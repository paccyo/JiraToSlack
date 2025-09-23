import os
import sys
import json
import argparse
from pathlib import Path

# Allow local imports
sys.path.append(str(Path(__file__).resolve().parents[1]))
from lib.jira_client import JiraClient  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="Story points sum (total/done/notDone)")
    parser.add_argument("--scope", choices=["project", "sprint"], default=os.getenv("SP_SCOPE", "sprint"))
    parser.add_argument("--project", help="Project key when scope=project")
    args = parser.parse_args()

    jc = JiraClient()
    sp_field = jc.resolve_story_points_field()

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

    # fetch issues and sum points by done/notDone
    code, issues, err = jc.search_paginated(base, fields=[sp_field, "status"], batch=100)
    if code != 200:
        print(err or "課題取得に失敗", file=sys.stderr)
        return 1

    total = 0.0
    done = 0.0

    for iss in issues:
        f = iss.get("fields") or {}
        val = f.get(sp_field)
        try:
            w = float(val) if val is not None else 0.0
        except Exception:
            w = 0.0
        total += w
        cat = ((f.get("status") or {}).get("statusCategory") or {}).get("key")
        if cat == "done":
            done += w

    out = {**meta, "fieldId": sp_field, "total": total, "done": done, "notDone": max(0.0, total - done)}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
