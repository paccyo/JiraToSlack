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
    parser = argparse.ArgumentParser(description="Jira status counts (project or sprint scope)")
    parser.add_argument("--scope", choices=["project", "sprint"], default=os.getenv("STATUS_COUNTS_SCOPE", "project"))
    parser.add_argument("--mode", choices=["approx", "aggregate"], default=os.getenv("STATUS_COUNTS_MODE", "approx"))
    parser.add_argument("--project", help="Project key override (when scope=project)")
    args = parser.parse_args()

    jc = JiraClient()
    scope = (args.scope or os.getenv("STATUS_COUNTS_SCOPE", "project")).lower()  # 'project' or 'sprint'
    key: Optional[str] = None
    sprint: Optional[Dict[str, Any]] = None
    if scope == "sprint":
        code_sp, sprint, err_sp = jc.resolve_active_sprint()
        if code_sp != 200 or not sprint:
            print(err_sp or "アクティブスプリントの解決に失敗", file=sys.stderr)
            return 1
    else:
        key = (args.project or jc.resolve_project_key())
        if not key:
            print("プロジェクトキーの解決に失敗", file=sys.stderr)
            return 1

    # Option: single-pass aggregation via fields=status (may be slow for very large sets)
    mode = (args.mode or os.getenv("STATUS_COUNTS_MODE", "approx")).lower()  # 'approx' or 'aggregate'

    # Get all statuses for the project to stabilize ordering (best-effort)
    statuses: List[str] = []
    code_s, data_s, _ = jc.api_get(f"{jc.domain}/rest/api/3/project/{key}/statuses")
    if code_s == 200 and isinstance(data_s, list) and data_s:
        try:
            # data_s is list of issueType -> {statuses: [...]}
            seen = set()
            for it in data_s:
                for st in (it.get("statuses") or []):
                    name = str(st.get("name"))
                    if name not in seen:
                        seen.add(name)
                        statuses.append(name)
        except Exception:
            statuses = []

    total = 0
    by_status: List[Dict[str, Any]] = []

    if mode == "aggregate":
        # Single search, aggregate client-side
        if scope == "sprint" and sprint:
            jql = f"Sprint={sprint.get('id')}"
        else:
            jql = f"project={key}"
        code, issues, err = jc.search_paginated(jql, fields=["status"])  # may be heavy
        if code != 200:
            print(err or "検索に失敗", file=sys.stderr)
            return 1
        counts: Dict[str, int] = {}
        for iss in issues:
            st = ((iss.get("fields") or {}).get("status") or {}).get("name") or "(unknown)"
            counts[st] = counts.get(st, 0) + 1
        total = sum(counts.values())
        # keep requested ordering if available
        names = statuses or sorted(counts.keys())
        for name in names:
            c = counts.get(name, 0)
            if c:
                by_status.append({"status": name, "count": c, "ratio": (c / total) if total else 0.0})
        # include any missing statuses
        for name, c in counts.items():
            if not any(x["status"] == name for x in by_status):
                by_status.append({"status": name, "count": c, "ratio": (c / total) if total else 0.0})
    else:
        # Approx mode: first total, then per-status quick counts
        if scope == "sprint" and sprint:
            base_jql = f"Sprint={sprint.get('id')}"
        else:
            base_jql = f"project={key}"
        code_t, tot_val, err_t = jc.approximate_count(base_jql)
        if code_t != 200 or tot_val is None:
            print(err_t or "件数取得に失敗", file=sys.stderr)
            return 1
        total = int(tot_val)
        # If we didn't get statuses list, fallback by sampling issues
        if not statuses:
            # fallback: fetch a page and infer
            code_f, issues_f, _ = jc.search_paginated(f"project={key}", fields=["status"], batch=50)
            if code_f == 200:
                tmp = set()
                for iss in issues_f:
                    nm = ((iss.get("fields") or {}).get("status") or {}).get("name")
                    if nm:
                        tmp.add(str(nm))
                statuses = sorted(tmp)
        # Now estimate per-status counts
        for name in statuses:
            esc = str(name).replace('"', '\\"')
            q = f'{base_jql} AND status="{esc}"'
            code_c, cnt, _ = jc.approximate_count(q)
            by_status.append({
                "status": name,
                "count": int(cnt or 0),
                "ratio": (int(cnt or 0) / total) if total else 0.0,
            })

    out = {
        "scope": scope,
        "project": key,
        "sprint": {"id": sprint.get("id"), "name": sprint.get("name")} if sprint else None,
        "total": total,
        "byStatus": by_status,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
