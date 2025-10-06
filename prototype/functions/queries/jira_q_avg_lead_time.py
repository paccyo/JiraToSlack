import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

# Allow local imports
try:
    from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded
    from prototype.local_cli.Loder.jira_client import JiraClient  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for direct execution
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "prototype").exists():
            sys.path.append(str(parent))
            break
    from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded  # type: ignore
    from prototype.local_cli.Loder.jira_client import JiraClient  # type: ignore


ensure_env_loaded()

JST = timezone(timedelta(hours=9))


def parse_iso(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Average lead time (created -> resolutiondate)")
    parser.add_argument("--scope", choices=["project", "sprint"], default=os.getenv("LT_SCOPE", "project"))
    parser.add_argument("--project", help="Project key when scope=project")
    parser.add_argument("--days", type=int, default=int(os.getenv("LT_DAYS", "28")))
    parser.add_argument("--unit", choices=["hours", "days"], default=os.getenv("LT_UNIT", "days"))
    args = parser.parse_args()

    jc = JiraClient()

    since = datetime.now(tz=JST) - timedelta(days=args.days)

    if args.scope == "sprint":
        code_sp, sprint, err_sp = jc.resolve_active_sprint()
        if code_sp != 200 or not sprint:
            print(err_sp or "アクティブスプリントが見つかりません", file=sys.stderr)
            return 1
        base = f"Sprint={sprint.get('id')}"
        meta = {"scope": "sprint", "sprint": {"id": sprint.get("id"), "name": sprint.get("name")}}
    else:
        key = args.project or jc.resolve_project_key()
        if not key:
            print("プロジェクトキーの解決に失敗", file=sys.stderr)
            return 1
        base = f"project={key}"
        meta = {"scope": "project", "project": key}

    # fetch only resolved issues in window
    jql = f"{base} AND resolutiondate >= -{args.days}d AND resolutiondate <= now()"
    code, issues, err = jc.search_paginated(jql, fields=["created", "resolutiondate"], batch=100)
    if code != 200:
        print(err or "課題取得に失敗", file=sys.stderr)
        return 1

    durations: List[float] = []
    for iss in issues:
        f = iss.get("fields") or {}
        c = parse_iso(f.get("created"))
        r = parse_iso(f.get("resolutiondate"))
        if not c or not r:
            continue
        dur = (r - c).total_seconds()
        if dur >= 0:
            durations.append(dur)

    denom = 3600.0 if args.unit == "hours" else 86400.0
    count = len(durations)
    avg = (sum(durations) / count / denom) if count else 0.0
    p50 = 0.0
    p95 = 0.0
    mx = 0.0
    if count:
        s = sorted(durations)
        p50 = s[int(0.5 * (count - 1))] / denom
        p95 = s[int(0.95 * (count - 1))] / denom
        mx = s[-1] / denom

    out = {**meta, "windowDays": args.days, "unit": args.unit,
           "count": count, "avg": avg, "p50": p50, "p95": p95, "max": mx}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
