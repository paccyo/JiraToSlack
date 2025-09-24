import sys
import json
import argparse
from pathlib import Path

# Allow local imports
sys.path.append(str(Path(__file__).resolve().parents[1]))
from lib.jira_client import JiraClient  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="Count all subtasks in project (independent of sprint)")
    parser.add_argument("--project", help="Project key; if omitted resolves from env/board", default=None)
    args = parser.parse_args()

    jc = JiraClient()

    # Resolve project key
    key = args.project or jc.resolve_project_key()
    if not key:
        print("プロジェクトキーの解決に失敗", file=sys.stderr)
        return 1

    # 補助: subTaskIssueTypes() が使えない環境向けに、サブタスク種別名での集計を試す
    def count_by_search(jql: str) -> tuple[int, int | None, str]:
        code_s, data_s, err_s = jc.api_get(f"{jc.domain}/rest/api/3/search", params={"jql": jql, "maxResults": 0})
        if code_s == 200 and isinstance(data_s, dict):
            try:
                return 200, int(data_s.get("total", 0)), ""
            except Exception:
                return 200, None, "totalの解析に失敗"
        return code_s, None, err_s

    def try_fallback_by_names() -> tuple[int | None, int | None, str]:
        code_it, data_it, err_it = jc.api_get(f"{jc.domain}/rest/api/3/issuetype")
        if code_it != 200 or not isinstance(data_it, list):
            return None, None, err_it or "種別一覧の取得に失敗"
        names = []
        for it in data_it:
            try:
                if bool(it.get("subtask")) and it.get("name"):
                    names.append(str(it.get("name")))
            except Exception:
                continue
        if not names:
            return None, None, "サブタスク種別が見つかりません"
        quoted = ",".join(['"{}"'.format(n.replace('"', '\\"')) for n in names])
        jql_total = f"project={key} AND type in ({quoted})"
        jql_done = f"{jql_total} AND statusCategory = \"Done\""
        c1, t1, _ = count_by_search(jql_total)
        c2, d1, _ = count_by_search(jql_done)
        if (c1 == 200 and t1 is not None) and (c2 == 200 and d1 is not None):
            return int(t1), int(d1), ""
        return None, None, "フォールバック集計に失敗"

    def count_for_project(pkey: str) -> tuple[int, int, str | None]:
        base = f"project={pkey} AND type in subTaskIssueTypes()"
        code_t, total_cnt, err_t = count_by_search(base)
        code_d, done_cnt, err_d = count_by_search(f"{base} AND statusCategory = \"Done\"")
        # If primary returned 0 or None while project likely has subtasks, attempt fallback chain
        use_fallback = (code_t != 200 or total_cnt is None) or (code_d != 200 or done_cnt is None) or ((total_cnt == 0) and (done_cnt == 0))
        if use_fallback:
            ft, fd, _ = try_fallback_by_names()
            if ft is not None and fd is not None:
                total_cnt, done_cnt = ft, fd
                code_t = code_d = 200
            else:
                # Second fallback: detect subtasks via parent field
                jql_total2 = f"project={pkey} AND parent is not EMPTY"
                jql_done2 = f"{jql_total2} AND statusCategory = \"Done\""
                c3, t2, _ = count_by_search(jql_total2)
                c4, d2, _ = count_by_search(jql_done2)
                if (c3 == 200 and t2 is not None) and (c4 == 200 and d2 is not None):
                    total_cnt, done_cnt = int(t2), int(d2)
                    code_t = code_d = 200
                else:
                    # Final fallback: scan project issues and filter by issuetype.subtask flag
                    c5, issues, _ = jc.search_paginated(f"project={pkey}", fields=["issuetype", "status", "parent"], batch=100)
                    if c5 == 200:
                        t3 = 0
                        d3 = 0
                        for iss in issues:
                            f = (iss or {}).get("fields") or {}
                            it = (f.get("issuetype") or {})
                            is_sub = bool(it.get("subtask")) or (f.get("parent") is not None)
                            if is_sub:
                                t3 += 1
                                if jc.is_done(f.get("status")):
                                    d3 += 1
                        total_cnt, done_cnt = t3, d3
                        code_t = code_d = 200
        if code_t != 200 or total_cnt is None:
            return 0, 0, err_t or "総数の取得に失敗"
        if code_d != 200 or done_cnt is None:
            return int(total_cnt), 0, err_d or "完了数の取得に失敗"
        return int(total_cnt), int(done_cnt), None

    # Primary: single project
    total_cnt, done_cnt, err_single = count_for_project(key)

    # If still zero, aggregate across all projects linked to the resolved board
    projects_used = [key]
    if total_cnt == 0 and done_cnt == 0:
        code_b, board, _ = jc.resolve_board()
        if code_b == 200 and board and board.get("id"):
            b_id = board.get("id")
            code_p, p_data, _ = jc.api_get(f"{jc.domain}/rest/agile/1.0/board/{b_id}/project")
            if code_p == 200 and p_data:
                plist = p_data.get("values") or p_data.get("projects") or []
                total_sum = 0
                done_sum = 0
                proj_keys = []
                for pr in plist:
                    pkey = pr.get("key") or pr.get("id")
                    if not pkey:
                        continue
                    pkey = str(pkey)
                    t, d, _ = count_for_project(pkey)
                    total_sum += int(t)
                    done_sum += int(d)
                    proj_keys.append(pkey)
                if total_sum or done_sum:
                    total_cnt, done_cnt = total_sum, done_sum
                    projects_used = proj_keys

    out = {
        "project": key,
        "total": int(total_cnt),
        "done": int(done_cnt),
        "notDone": int(total_cnt) - int(done_cnt),
    }
    if projects_used and (len(projects_used) > 1 or projects_used[0] != key):
        out["projectsFromBoard"] = projects_used
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
