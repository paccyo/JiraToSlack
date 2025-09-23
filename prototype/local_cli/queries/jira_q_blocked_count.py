import os
import sys
import json
import argparse
from typing import Any, Dict, List
from pathlib import Path

# Allow local imports
sys.path.append(str(Path(__file__).resolve().parents[1]))
from lib.jira_client import JiraClient  # type: ignore


BLOCK_STRINGS = {"is blocked by", "Blocks", "blocks", "is blocked by"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Blocked issues count (issue links)")
    parser.add_argument("--scope", choices=["project", "sprint"], default=os.getenv("BL_SCOPE", "sprint"))
    parser.add_argument("--project", help="Project key when scope=project")
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

    code, issues, err = jc.search_paginated(base, fields=["issuelinks"], batch=100)
    if code != 200:
        print(err or "課題取得に失敗", file=sys.stderr)
        return 1

    blocked_count = 0
    by_issue: List[Dict[str, Any]] = []

    for iss in issues:
        links = ((iss.get("fields") or {}).get("issuelinks") or [])
        is_blocked = False
        for lk in links:
            t = (lk.get("type") or {})
            inward = (t.get("inward") or "").lower()
            outward = (t.get("outward") or "").lower()
            if inward in {"is blocked by", "はブロックされています"} or outward in {"blocks", "ブロックする"}:
                is_blocked = True
                break
        if is_blocked:
            blocked_count += 1
            by_issue.append({"key": iss.get("key")})

    out = {**meta, "blockedCount": blocked_count, "byIssue": by_issue}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
