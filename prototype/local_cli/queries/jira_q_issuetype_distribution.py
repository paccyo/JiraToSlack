import os
import sys
import json
import argparse
from typing import Any, Dict, List
from pathlib import Path

# Allow local imports
sys.path.append(str(Path(__file__).resolve().parents[1]))
from lib.jira_client import JiraClient  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue type distribution")
    parser.add_argument("--scope", choices=["project", "sprint"], default=os.getenv("IT_SCOPE", "project"))
    parser.add_argument("--project", help="Project key when scope=project")
    parser.add_argument("--mode", choices=["approx", "aggregate"], default=os.getenv("IT_MODE", "approx"))
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
        code, issues, err = jc.search_paginated(base, fields=["issuetype"], batch=100)
        if code != 200:
            print(err or "課題取得に失敗", file=sys.stderr)
            return 1
        for iss in issues:
            name = (((iss.get("fields") or {}).get("issuetype") or {}).get("name")) or "(unknown)"
            counts[name] = counts.get(name, 0) + 1
        total = sum(counts.values())
    else:
        # approx mode: fetch available issue types in project and count per type
        # Note: for sprint scope, reuse project issue types
        key = jc.resolve_project_key()
        code_t, data_t, _ = jc.api_get(f"{jc.domain}/rest/api/3/project/{key}")
        type_names: List[str] = []
        if code_t == 200 and data_t:
            # optional: get via /issuetype if needed
            code_it, data_it, _ = jc.api_get(f"{jc.domain}/rest/api/3/issuetype")
            if code_it == 200 and isinstance(data_it, list):
                type_names = sorted({str(t.get("name")) for t in data_it if t.get("name")})
        # fallback: sample
        if not type_names:
            code_s, sample, _ = jc.search_paginated(base, fields=["issuetype"], batch=50)
            if code_s == 200:
                type_names = sorted({(((x.get("fields") or {}).get("issuetype") or {}).get("name")) or "(unknown)" for x in sample})
        # count approximate per type
        for name in type_names:
            esc = str(name).replace('"', '\\"')
            jql = f'{base} AND issuetype = "{esc}"'
            code_c, cnt, _ = jc.approximate_count(jql)
            counts[name] = int(cnt or 0)
        total = sum(counts.values())

    by_type = [
        {"name": k, "count": v, "ratio": (v / total) if total else 0.0}
        for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    out = {**meta, "total": total, "byType": by_type}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
