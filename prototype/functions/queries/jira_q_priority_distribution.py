import os
import sys
import json
import argparse
from typing import Any, Dict, List
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Priority distribution")
    parser.add_argument("--scope", choices=["project", "sprint"], default=os.getenv("PR_SCOPE", "project"))
    parser.add_argument("--project", help="Project key when scope=project")
    parser.add_argument("--mode", choices=["approx", "aggregate"], default=os.getenv("PR_MODE", "approx"))
    args = parser.parse_args()

    jc = JiraClient()

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

    counts: Dict[str, int] = {}
    total = 0

    if args.mode == "aggregate":
        code, issues, err = jc.search_paginated(base, fields=["priority"], batch=100)
        if code != 200:
            print(err or "課題取得に失敗", file=sys.stderr)
            return 1
        for iss in issues:
            name = (((iss.get("fields") or {}).get("priority") or {}).get("name")) or "(unknown)"
            counts[name] = counts.get(name, 0) + 1
        total = sum(counts.values())
    else:
        # approx mode: fetch available priorities and count per priority
        code_p, data_p, _ = jc.api_get(f"{jc.domain}/rest/api/3/priority")
        names: List[str] = []
        if code_p == 200 and isinstance(data_p, list):
            names = [str(p.get("name")) for p in data_p if p.get("name")]
        if not names:
            code_s, sample, _ = jc.search_paginated(base, fields=["priority"], batch=50)
            if code_s == 200:
                names = sorted({(((x.get("fields") or {}).get("priority") or {}).get("name")) or "(unknown)" for x in sample})
        for name in names:
            esc = str(name).replace('"', '\\"')
            jql = f'{base} AND priority = "{esc}"'
            code_c, cnt, _ = jc.approximate_count(jql)
            counts[name] = int(cnt or 0)
        total = sum(counts.values())

    by_pri = [
        {"name": k, "count": v, "ratio": (v / total) if total else 0.0}
        for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    out = {**meta, "total": total, "byPriority": by_pri}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
