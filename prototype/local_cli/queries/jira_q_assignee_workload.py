import os
import sys
import json
import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Assignee workload: count by assignee (done/not)")
    parser.add_argument("--scope", choices=["project", "sprint"], default=os.getenv("WL_SCOPE", "sprint"))
    parser.add_argument("--project", help="Project key when scope=project")
    args = parser.parse_args()

    jc = JiraClient()

    # build base JQL
    if args.scope == "sprint":
        code_sp, sprint, err_sp = jc.resolve_active_sprint()
        if code_sp != 200 or not sprint:
            print(err_sp or "アクティブスプリントが見つかりません", file=sys.stderr)
            return 1
        base_jql = f"Sprint={sprint.get('id')}"
        scope_meta = {"scope": "sprint", "sprint": {"id": sprint.get("id"), "name": sprint.get("name")}}
    else:
        key = args.project or jc.resolve_project_key()
        if not key:
            print("プロジェクトキーの解決に失敗", file=sys.stderr)
            return 1
        base_jql = f"project={key}"
        scope_meta = {"scope": "project", "project": key}

    # fetch issues with fields
    code, issues, err = jc.search_paginated(base_jql, fields=["assignee", "status"], batch=100)
    if code != 200:
        print(err or "課題取得に失敗", file=sys.stderr)
        return 1

    by_assignee: Dict[str, Dict[str, int]] = {}
    unassigned = {"total": 0, "done": 0, "notDone": 0}

    for iss in issues:
        f = iss.get("fields") or {}
        assignee = f.get("assignee") or None
        name = (assignee or {}).get("displayName") if assignee else None
        st = f.get("status") or {}
        cat = (st.get("statusCategory") or {}).get("key")
        is_done = cat == "done"

        if not name:
            unassigned["total"] += 1
            if is_done:
                unassigned["done"] += 1
            else:
                unassigned["notDone"] += 1
            continue

        row = by_assignee.setdefault(name, {"total": 0, "done": 0, "notDone": 0})
        row["total"] += 1
        if is_done:
            row["done"] += 1
        else:
            row["notDone"] += 1

    out = {
        **scope_meta,
        "byAssignee": [
            {"name": k, **v} for k, v in sorted(by_assignee.items(), key=lambda x: (-x[1]["total"], x[0]))
        ],
        "unassigned": unassigned,
    }

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
