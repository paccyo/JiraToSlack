import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

# Allow local imports
try:
    from prototype.local_cli.lib.env_loader import ensure_env_loaded
    from prototype.local_cli.lib.jira_client import JiraClient  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for direct execution
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from env_loader import ensure_env_loaded  # type: ignore
    from lib.jira_client import JiraClient  # type: ignore


ensure_env_loaded()

JST = timezone(timedelta(hours=9))


def parse_iso(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None


REOPEN_STATUS_NAMES = {"reopened", "re-opened", "再オープン", "再オープン済み"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Reopened count via changelog")
    parser.add_argument("--scope", choices=["project", "sprint"], default=os.getenv("REOPEN_SCOPE", "sprint"))
    parser.add_argument("--project", help="Project key when scope=project")
    parser.add_argument("--since", help="ISO datetime; default sprint start or now-28d")
    parser.add_argument("--until", help="ISO datetime; default sprint end or now")
    args = parser.parse_args()

    jc = JiraClient()

    since = parse_iso(args.since)
    until = parse_iso(args.until)
    meta: Dict[str, Any] = {}

    if args.scope == "sprint":
        code_sp, sprint, err_sp = jc.resolve_active_sprint()
        if code_sp != 200 or not sprint:
            print(err_sp or "アクティブスプリントが見つかりません", file=sys.stderr)
            return 1
        base = f"Sprint={sprint.get('id')}"
        meta.update({"scope": "sprint", "sprint": {"id": sprint.get("id"), "name": sprint.get("name")}})
        if not since:
            since = parse_iso(sprint.get("startDate"))
        if not until:
            until = parse_iso(sprint.get("endDate")) or datetime.now(tz=JST)
    else:
        key = args.project or jc.resolve_project_key()
        if not key:
            print("プロジェクトキーの解決に失敗", file=sys.stderr)
            return 1
        base = f"project={key}"
        meta.update({"scope": "project", "project": key})
        if not since:
            since = datetime.now(tz=JST) - timedelta(days=28)
        if not until:
            until = datetime.now(tz=JST)

    if not since:
        since = datetime.now(tz=JST) - timedelta(days=28)
    if not until:
        until = datetime.now(tz=JST)

    # Fetch issues in scope (keys/ids), then per-issue changelog
    code, issues, err = jc.search_paginated(base, fields=["status"], batch=100)
    if code != 200:
        print(err or "課題取得に失敗", file=sys.stderr)
        return 1

    total_reopened = 0
    by_issue: List[Dict[str, Any]] = []

    for iss in issues:
        iid = iss.get("id")
        ikey = iss.get("key")
        code_i, data_i, _ = jc.api_get(f"{jc.domain}/rest/api/3/issue/{iid}", params={"expand": "changelog"})
        if code_i != 200 or not data_i:
            continue
        histories = ((data_i.get("changelog") or {}).get("histories") or [])
        count = 0
        last = None
        for h in histories:
            t = parse_iso(h.get("created"))
            if not t:
                continue
            if t < since or t > until:
                continue
            for it in (h.get("items") or []):
                field = it.get("field")
                if field == "status":
                    to_name = (it.get("toString") or "").strip()
                    if to_name and to_name.lower() in REOPEN_STATUS_NAMES:
                        count += 1
                        last = t
                elif field == "resolution":
                    from_s = (it.get("fromString") or "").strip()
                    to_s = (it.get("toString") or "").strip()
                    # resolution cleared (from set -> empty) counts as reopen
                    if from_s and not to_s:
                        count += 1
                        last = t
        if count > 0:
            total_reopened += count
            by_issue.append({"key": ikey, "count": count, "lastAt": last.isoformat() if last else None})

    out = {**meta, "window": {"since": since.isoformat(), "until": until.isoformat()},
           "totalReopened": total_reopened, "byIssue": by_issue}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
