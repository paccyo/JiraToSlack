import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth


def load_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        print(f"環境変数が未設定です: {key}", file=sys.stderr)
        sys.exit(2)
    return value


def maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / ".env",
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=False)


def api_get(
    url: str, auth: HTTPBasicAuth, params: Optional[Dict[str, Any]] = None
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    try:
        resp = requests.get(
            url,
            auth=auth,
            headers={"Accept": "application/json"},
            params=params,
            timeout=30,
        )
    except requests.RequestException as e:
        return 0, None, f"HTTPリクエストエラー: {e}"

    if resp.status_code == 200:
        try:
            return 200, resp.json(), ""
        except json.JSONDecodeError:
            return 200, None, "レスポンスのJSON解析に失敗しました"
    else:
        return resp.status_code, None, resp.text


def api_post(
    url: str, auth: HTTPBasicAuth, json_body: Dict[str, Any]
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    try:
        resp = requests.post(
            url,
            json=json_body,
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as e:
        return 0, None, f"HTTPリクエストエラー: {e}"

    if resp.status_code == 200:
        try:
            return 200, resp.json(), ""
        except json.JSONDecodeError:
            return 200, None, "レスポンスのJSON解析に失敗しました"
    else:
        return resp.status_code, None, resp.text


def resolve_board(JIRA_DOMAIN: str, auth: HTTPBasicAuth) -> Tuple[int, Optional[Dict[str, Any]], str]:
    board_id = os.getenv("JIRA_BOARD_ID")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    # 1) 数値ID指定
    if board_id and board_id.isdigit():
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}", auth)
        if code == 200 and data:
            return 200, data, ""
        return code, None, f"ボードID {board_id} の取得に失敗: {err}"

    # 2) 名称指定: プロジェクト配下→全体の順
    if board_id and not board_id.isdigit():
        params = {"maxResults": 50}
        if project_key:
            params["projectKeyOrId"] = project_key
        code_b, data_b, err_b = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params=params)
        items: List[Dict[str, Any]] = []
        if code_b == 200 and data_b:
            items.extend(data_b.get("values", []))
        else:
            return code_b, None, f"ボード一覧取得に失敗: {err_b}"

        exact = [x for x in items if str(x.get("name", "")).lower() == board_id.lower()]
        if exact:
            return 200, exact[0], ""
        partial = [x for x in items if board_id.lower() in str(x.get("name", "")).lower()]
        if partial:
            return 200, partial[0], ""

        code_b2, data_b2, err_b2 = api_get(
            f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params={"maxResults": 50}
        )
        if code_b2 == 200 and data_b2:
            items2 = data_b2.get("values", [])
            exact = [x for x in items2 if str(x.get("name", "")).lower() == board_id.lower()]
            if exact:
                return 200, exact[0], ""
            partial = [x for x in items2 if board_id.lower() in str(x.get("name", "")).lower()]
            if partial:
                return 200, partial[0], ""
        else:
            return code_b2, None, f"ボード一覧取得に失敗: {err_b2}"
        return 404, None, f"ボード名 '{board_id}' は見つかりませんでした"

    # 3) 指定なし: プロジェクト配下のScrumボード→全体。候補が複数でも先頭を採用（PoC）。
    params = {"maxResults": 50}
    if project_key:
        params["projectKeyOrId"] = project_key
    code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params=params)
    if code == 200 and data and data.get("values"):
        return 200, data.get("values")[0], ""

    # 全体から
    code2, data2, err2 = api_get(
        f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params={"maxResults": 50}
    )
    if code2 == 200 and data2 and data2.get("values"):
        return 200, data2.get("values")[0], ""
    if code2 != 200:
        return code2, None, f"ボード一覧取得に失敗: {err2}"
    return 404, None, "ボードが見つかりませんでした"


def resolve_active_sprint(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth, board_id: int
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    sprint_id_env = os.getenv("JIRA_SPRINT_ID")
    if sprint_id_env:
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/sprint/{sprint_id_env}", auth)
        if code == 200 and data:
            return 200, data, ""
        return code, None, f"スプリントID {sprint_id_env} の取得に失敗: {err}"

    params = {"state": "active", "maxResults": 50}
    code, data, err = api_get(
        f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}/sprint", auth, params=params
    )
    if code != 200 or not data:
        return code, None, f"アクティブスプリントの取得に失敗: {err}"

    sprints = data.get("values", [])
    if not sprints:
        return 404, None, "アクティブなスプリントが見つかりません"
    if len(sprints) > 1:
        msg = "複数のアクティブスプリントが見つかりました。JIRA_SPRINT_ID を設定してください:\n" + "\n".join(
            [f"  - {s.get('name')} (id={s.get('id')})" for s in sprints]
        )
        return 409, None, msg
    return 200, sprints[0], ""


def search_issues_jql(
    JIRA_DOMAIN: str,
    auth: HTTPBasicAuth,
    jql: str,
    fields: Optional[List[str]] = None,
    batch_size: int = 100,
) -> Tuple[int, Optional[List[Dict[str, Any]]], str]:
    start_at = 0
    all_issues: List[Dict[str, Any]] = []
    fields = fields or ["summary", "issuetype", "status", "subtasks", "assignee"]

    while True:
        # Prefer GET /search with params; fallback to POST if needed
        params = {
            "jql": jql,
            "fields": ",".join(fields),
            "startAt": start_at,
            "maxResults": batch_size,
        }
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/api/3/search", auth, params=params)
        if code != 200 or not data:
            body = {
                "jql": jql,
                "fields": fields,
                "startAt": start_at,
                "maxResults": batch_size,
            }
            code2, data2, err2 = api_post(f"{JIRA_DOMAIN}/rest/api/3/search", auth, body)
            if code2 != 200 or not data2:
                return code, None, f"JQL検索に失敗: {err or err2}"
            data = data2

        # Response can be { issues, total } or other shapes; normalize
        issues = data.get("issues") if isinstance(data, dict) else None
        if issues is None and isinstance(data, dict):
            # Try alternative keys
            issues = data.get("results") or data.get("data")
        if issues is None:
            return 200, [], ""

        total = int(data.get("total", len(issues))) if isinstance(data, dict) else len(issues)
        all_issues.extend(issues)

        start_at += len(issues)
        if start_at >= total or not issues:
            break

    return 200, all_issues, ""


def agile_list_issues_in_sprint(
    JIRA_DOMAIN: str,
    auth: HTTPBasicAuth,
    sprint_id: int,
    project_key: Optional[str],
    fields: Optional[List[str]] = None,
    batch_size: int = 100,
) -> Tuple[int, Optional[List[Dict[str, Any]]], str]:
    start_at = 0
    all_issues: List[Dict[str, Any]] = []
    fields = fields or ["summary", "issuetype", "status", "subtasks", "assignee"]
    jql_parts: List[str] = ["issuetype not in subTaskIssueTypes()"]
    if project_key:
        jql_parts.insert(0, f"project={project_key}")
    jql = " AND ".join(jql_parts)

    while True:
        params = {
            "jql": jql,
            "fields": ",".join(fields),
            "startAt": start_at,
            "maxResults": batch_size,
        }
        code, data, err = api_get(
            f"{JIRA_DOMAIN}/rest/agile/1.0/sprint/{sprint_id}/issue", auth, params=params
        )
        if code != 200 or not data:
            return code, None, f"スプリント {sprint_id} の課題取得に失敗: {err}"

        issues = data.get("issues", [])
        total = int(data.get("total", 0))
        all_issues.extend(issues)

        start_at += len(issues)
        if start_at >= total or not issues:
            break

    return 200, all_issues, ""


def ensure_subtask_fields(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth, subtask: Dict[str, Any]
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    fields = subtask.get("fields")
    if fields and fields.get("status") and fields.get("summary"):
        return 200, subtask, ""

    sub_id = subtask.get("id") or subtask.get("key")
    if not sub_id:
        return 400, None, "サブタスクのID/Keyが取得できませんでした"

    code, data, err = api_get(
        f"{JIRA_DOMAIN}/rest/api/3/issue/{sub_id}", auth, params={"fields": "summary,status"}
    )
    if code != 200 or not data:
        return code, None, f"サブタスク詳細取得に失敗: {err}"

    # 期待する形に整形
    subtask["fields"] = subtask.get("fields", {}) or {}
    subtask["fields"].update({
        "summary": data.get("fields", {}).get("summary"),
        "status": data.get("fields", {}).get("status"),
    })
    return 200, subtask, ""


def is_done(status_field: Optional[Dict[str, Any]]) -> Optional[bool]:
    if not status_field:
        return None
    cat = (status_field or {}).get("statusCategory") or {}
    key = cat.get("key")
    if key == "done":
        return True
    if key in {"new", "indeterminate"}:
        return False
    return None


def try_infer_project_key_from_board(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth, board: Dict[str, Any]
) -> Optional[str]:
    loc = (board or {}).get("location") or {}
    pkey = loc.get("projectKey")
    if pkey:
        return str(pkey)
    bid = board.get("id")
    try:
        bid_int = int(bid)
    except Exception:
        return None
    code, detail, _ = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board/{bid_int}", auth)
    if code == 200 and detail:
        loc = (detail or {}).get("location") or {}
        pkey = loc.get("projectKey")
        if pkey:
            return str(pkey)
    return None


def list_and_print_subtasks(
    JIRA_DOMAIN: str,
    auth: HTTPBasicAuth,
    issues_source: List[Dict[str, Any]] | None,
    header: str,
) -> int:
    issues = issues_source or []

    print(header)
    print("")

    total_parents = 0
    total_subtasks = 0
    total_done = 0

    for issue in issues:
        fields = issue.get("fields", {})
        subtasks = fields.get("subtasks", []) or []
        if not subtasks:
            continue

        total_parents += 1
        parent_key = issue.get("key")
        parent_summary = fields.get("summary")
        assignee = (fields.get("assignee") or {}).get("displayName")
        print(f"親タスク {parent_key} - {parent_summary}{' / 担当: ' + assignee if assignee else ''}")

        parent_done = 0
        for sub in subtasks:
            code_s, sub_full, err_s = ensure_subtask_fields(JIRA_DOMAIN, auth, sub)
            if code_s != 200 or not sub_full:
                print(f"  - {sub.get('key') or sub.get('id')} 取得失敗: {err_s}")
                continue

            sub_key = sub_full.get("key") or sub_full.get("id")
            sub_fields = sub_full.get("fields", {})
            sub_summary = sub_fields.get("summary")
            status = sub_fields.get("status")
            done_flag = is_done(status)

            status_name = (status or {}).get("name") or "(不明)"
            badge = "Done" if done_flag else ("Not Done" if done_flag is False else "Unknown")
            print(f"  - [{badge}] {sub_key} - {sub_summary} (Status: {status_name})")

            total_subtasks += 1
            if done_flag:
                total_done += 1
                parent_done += 1

        print(f"    小タスク完了: {parent_done}/{len(subtasks)}")
        print("")

    if total_subtasks == 0:
        print("小タスクは見つかりませんでした。")
    else:
        print("合計")
        print(f"  親タスク数: {total_parents}")
        print(f"  小タスク数: {total_subtasks}")
        print(f"  完了: {total_done} / 未完了: {total_subtasks - total_done}")

    return 0


def main() -> int:
    maybe_load_dotenv()
    JIRA_DOMAIN = load_env("JIRA_DOMAIN").rstrip("/")
    email = load_env("JIRA_EMAIL")
    api_token = load_env("JIRA_API_TOKEN")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    auth = HTTPBasicAuth(email, api_token)

    # 1) スプリントIDが指定されている場合はそれを優先
    sprint_id_env = os.getenv("JIRA_SPRINT_ID")
    if sprint_id_env:
        header = f"スプリント '{sprint_id_env}' 内の小タスク一覧"
        code, sprint_info, _ = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/sprint/{sprint_id_env}", auth)
        if code == 200 and sprint_info:
            header = f"スプリント '{sprint_info.get('name')}' 内の小タスク一覧"
        code_i, issues_i, err_i = agile_list_issues_in_sprint(
            JIRA_DOMAIN, auth, int(sprint_id_env), project_key, fields=["summary", "issuetype", "status", "subtasks", "assignee"]
        )
        if code_i != 200 or issues_i is None:
            print(err_i, file=sys.stderr)
            return 1
        return list_and_print_subtasks(JIRA_DOMAIN, auth, issues_i, header)

    # 2) まずボードを一意に解決
    code_b, board, err_b = resolve_board(JIRA_DOMAIN, auth)
    if code_b != 200 or not board:
        print(err_b, file=sys.stderr)
        return 1

    board_id = int(board.get("id"))
    board_name = board.get("name")
    print(f"使用ボード: {board_name} (id={board_id})")

    # プロジェクトキー未設定ならボードから推測
    if not project_key:
        inferred = try_infer_project_key_from_board(JIRA_DOMAIN, auth, board)
        if inferred:
            project_key = inferred
            print(f"推測したプロジェクトキー: {project_key}")

    # 3) アクティブスプリントを解決
    code_s, sprint, err_s = resolve_active_sprint(JIRA_DOMAIN, auth, board_id)
    if code_s != 200 or not sprint:
        print(err_s, file=sys.stderr)
        return 1

    sprint_id = int(sprint.get("id"))
    sprint_name = sprint.get("name")

    # 4) スプリント内の親タスクを取得し、小タスクを列挙
    code_i, issues_i, err_i = agile_list_issues_in_sprint(
        JIRA_DOMAIN, auth, sprint_id, project_key, fields=["summary", "issuetype", "status", "subtasks", "assignee"]
    )
    if code_i != 200 or issues_i is None:
        print(err_i, file=sys.stderr)
        return 1

    header = f"ボード '{board_name}' のアクティブスプリント '{sprint_name}' 内の小タスク一覧"
    return list_and_print_subtasks(JIRA_DOMAIN, auth, issues_i, header)


if __name__ == "__main__":
    sys.exit(main())
