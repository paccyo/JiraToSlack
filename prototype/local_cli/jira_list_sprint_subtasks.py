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


def resolve_board(jira_base_url: str, auth: HTTPBasicAuth) -> Tuple[int, Optional[Dict[str, Any]], str]:
    board_id = os.getenv("JIRA_BOARD_ID")
    if board_id:
        if board_id.isdigit():
            code, data, err = api_get(f"{jira_base_url}/rest/agile/1.0/board/{board_id}", auth)
            if code == 200 and data:
                return 200, data, ""
            return code, None, f"ボードID {board_id} の取得に失敗: {err}"
        else:
            # 名前で解決: プロジェクト配下→全体の順で探索
            project_key = os.getenv("JIRA_PROJECT_KEY")
            # まずプロジェクト配下
            params = {"type": "scrum", "maxResults": 50}
            if project_key:
                params["projectKeyOrId"] = project_key
            code_b, data_b, err_b = api_get(f"{jira_base_url}/rest/agile/1.0/board", auth, params=params)
            boards = []
            if code_b == 200 and data_b:
                boards.extend(data_b.get("values", []))
            else:
                return code_b, None, f"ボード一覧取得に失敗: {err_b}"

            def find_by_name(items, name):
                exact = [x for x in items if str(x.get("name", "")).lower() == name.lower()]
                if exact:
                    return exact
                return [x for x in items if name.lower() in str(x.get("name", "")).lower()]

            matches = find_by_name(boards, board_id)
            if not matches:
                # 全体で再取得
                code_b2, data_b2, err_b2 = api_get(
                    f"{jira_base_url}/rest/agile/1.0/board", auth, params={"type": "scrum", "maxResults": 50}
                )
                if code_b2 == 200 and data_b2:
                    boards = data_b2.get("values", [])
                    matches = find_by_name(boards, board_id)
                else:
                    return code_b2, None, f"ボード一覧取得に失敗: {err_b2}"

            if not matches:
                return 404, None, f"ボード名 '{board_id}' は見つかりませんでした"
            if len(matches) > 1:
                cand = ", ".join([f"{b.get('name')} (id={b.get('id')})" for b in matches[:10]])
                return 409, None, f"ボード名 '{board_id}' の候補が複数見つかりました: {cand}"
            return 200, matches[0], ""

    project_key = os.getenv("JIRA_PROJECT_KEY")
    if not project_key:
        return 400, None, "JIRA_BOARD_ID か JIRA_PROJECT_KEY のいずれかを設定してください"

    params = {"projectKeyOrId": project_key, "type": "scrum", "maxResults": 50}
    code, data, err = api_get(f"{jira_base_url}/rest/agile/1.0/board", auth, params=params)
    if code != 200 or not data:
        return code, None, f"ボード一覧取得に失敗: {err}"

    boards = data.get("values", [])
    if not boards:
        return 404, None, f"プロジェクト {project_key} に紐づくScrumボードが見つかりません"
    if len(boards) > 1:
        msg = "複数のボードが見つかりました。JIRA_BOARD_ID を設定してください:\n" + "\n".join(
            [f"  - {b.get('name')} (id={b.get('id')})" for b in boards]
        )
        return 409, None, msg
    return 200, boards[0], ""


def resolve_active_sprint(
    jira_base_url: str, auth: HTTPBasicAuth, board_id: int
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    sprint_id_env = os.getenv("JIRA_SPRINT_ID")
    if sprint_id_env:
        code, data, err = api_get(f"{jira_base_url}/rest/agile/1.0/sprint/{sprint_id_env}", auth)
        if code == 200 and data:
            return 200, data, ""
        return code, None, f"スプリントID {sprint_id_env} の取得に失敗: {err}"

    params = {"state": "active", "maxResults": 50}
    code, data, err = api_get(
        f"{jira_base_url}/rest/agile/1.0/board/{board_id}/sprint", auth, params=params
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
    jira_base_url: str,
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
        code, data, err = api_get(f"{jira_base_url}/rest/api/3/search", auth, params=params)
        if code != 200 or not data:
            body = {
                "jql": jql,
                "fields": fields,
                "startAt": start_at,
                "maxResults": batch_size,
            }
            code2, data2, err2 = api_post(f"{jira_base_url}/rest/api/3/search", auth, body)
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
    jira_base_url: str,
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
            f"{jira_base_url}/rest/agile/1.0/sprint/{sprint_id}/issue", auth, params=params
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
    jira_base_url: str, auth: HTTPBasicAuth, subtask: Dict[str, Any]
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    fields = subtask.get("fields")
    if fields and fields.get("status") and fields.get("summary"):
        return 200, subtask, ""

    sub_id = subtask.get("id") or subtask.get("key")
    if not sub_id:
        return 400, None, "サブタスクのID/Keyが取得できませんでした"

    code, data, err = api_get(
        f"{jira_base_url}/rest/api/3/issue/{sub_id}", auth, params={"fields": "summary,status"}
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


def list_and_print_subtasks(
    jira_base_url: str,
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
            code_s, sub_full, err_s = ensure_subtask_fields(jira_base_url, auth, sub)
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
    jira_base_url = load_env("JIRA_BASE_URL").rstrip("/")
    email = load_env("JIRA_EMAIL")
    api_token = load_env("JIRA_API_TOKEN")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    auth = HTTPBasicAuth(email, api_token)

    # 1) スプリントIDが指定されている場合はそれを優先
    sprint_id_env = os.getenv("JIRA_SPRINT_ID")
    if sprint_id_env:
        header = f"スプリント '{sprint_id_env}' 内の小タスク一覧"
        # 名前が取れれば差し替え
        code, sprint_info, _ = api_get(f"{jira_base_url}/rest/agile/1.0/sprint/{sprint_id_env}", auth)
        if code == 200 and sprint_info:
            header = f"スプリント '{sprint_info.get('name')}' 内の小タスク一覧"
        code_i, issues_i, err_i = agile_list_issues_in_sprint(
            jira_base_url, auth, int(sprint_id_env), project_key, fields=["summary", "issuetype", "status", "subtasks", "assignee"]
        )
        if code_i != 200 or issues_i is None:
            print(err_i, file=sys.stderr)
            return 1
        return list_and_print_subtasks(jira_base_url, auth, issues_i, header)

    # 2) ボードとアクティブスプリントを解決
    code, board, err = resolve_board(jira_base_url, auth)
    if code == 200 and board:
        board_id = int(board.get("id"))
        board_name = board.get("name")

        code, sprint, err = resolve_active_sprint(jira_base_url, auth, board_id)
        if code == 200 and sprint:
            sprint_id = int(sprint.get("id"))
            sprint_name = sprint.get("name")

            code_i, issues_i, err_i = agile_list_issues_in_sprint(
                jira_base_url, auth, sprint_id, project_key, fields=["summary", "issuetype", "status", "subtasks", "assignee"]
            )
            if code_i != 200 or issues_i is None:
                print(err_i, file=sys.stderr)
                return 1
            header = f"ボード '{board_name}' のアクティブスプリント '{sprint_name}' 内の小タスク一覧"
            return list_and_print_subtasks(jira_base_url, auth, issues_i, header)

        # スプリントが取れない場合は openSprints() にフォールバック
        warn = f"アクティブスプリント解決に失敗: {err}。openSprints() で代替します。"
        print(warn, file=sys.stderr)
    else:
        # ボードが取れない場合も openSprints() にフォールバック
        warn = f"ボード解決に失敗: {err}。openSprints() で代替します。"
        print(warn, file=sys.stderr)

    # 3) 全スクラムボードを走査し、アクティブスプリントを集計して取得
    boards: List[Dict[str, Any]] = []
    code_b, data_b, err_b = api_get(f"{jira_base_url}/rest/agile/1.0/board", auth, params={"type": "scrum", "maxResults": 50})
    if code_b == 200 and data_b:
        boards.extend(data_b.get("values", []))
        # ページング対応（必要に応じて）
        start_at = data_b.get("startAt", 0)
        max_results = data_b.get("maxResults", 50)
        total = data_b.get("total", len(boards))
        while start_at + max_results < total:
            start_at += max_results
            code_b2, data_b2, err_b2 = api_get(
                f"{jira_base_url}/rest/agile/1.0/board", auth, params={"type": "scrum", "maxResults": 50, "startAt": start_at}
            )
            if code_b2 == 200 and data_b2:
                boards.extend(data_b2.get("values", []))
            else:
                print(f"ボード一覧のページング取得に一部失敗: {err_b2}", file=sys.stderr)
                break
    else:
        print(f"ボード一覧取得に失敗: {err_b}", file=sys.stderr)

    sprint_ids: List[int] = []
    for b in boards:
        bid = b.get("id")
        if bid is None:
            continue
        code_s, data_s, err_s = api_get(
            f"{jira_base_url}/rest/agile/1.0/board/{bid}/sprint", auth, params={"state": "active", "maxResults": 50}
        )
        if code_s == 200 and data_s:
            for s in data_s.get("values", []) or []:
                sid = s.get("id")
                if isinstance(sid, int) and sid not in sprint_ids:
                    sprint_ids.append(sid)
        else:
            print(f"ボード {bid} のスプリント取得に失敗: {err_s}", file=sys.stderr)

    combined_issues: List[Dict[str, Any]] = []
    for sid in sprint_ids:
        code_i, issues_i, err_i = agile_list_issues_in_sprint(
            jira_base_url, auth, sid, project_key, fields=["summary", "issuetype", "status", "subtasks", "assignee"]
        )
        if code_i == 200 and issues_i:
            combined_issues.extend(issues_i)
        else:
            print(f"スプリント {sid} の課題取得に失敗: {err_i}", file=sys.stderr)

    header = f"プロジェクト '{project_key or '-'}' のアクティブスプリント(全ボード)内の小タスク一覧"
    return list_and_print_subtasks(jira_base_url, auth, combined_issues, header)


if __name__ == "__main__":
    sys.exit(main())
