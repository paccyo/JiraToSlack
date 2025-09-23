import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

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


def api_get(url: str, auth: HTTPBasicAuth, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Optional[Dict[str, Any]], str]:
    try:
        resp = requests.get(url, auth=auth, headers={"Accept": "application/json"}, params=params, timeout=30)
    except requests.RequestException as e:
        return 0, None, f"HTTPリクエストエラー: {e}"

    if resp.status_code == 200:
        try:
            return 200, resp.json(), ""
        except json.JSONDecodeError:
            return 200, None, "レスポンスのJSON解析に失敗しました"
    else:
        return resp.status_code, None, resp.text


def list_scrum_boards(JIRA_DOMAIN: str, auth: HTTPBasicAuth, project_key: Optional[str]) -> Tuple[int, List[Dict[str, Any]], str]:
    boards: List[Dict[str, Any]] = []
    params: Dict[str, Any] = {"type": "scrum", "maxResults": 50}
    if project_key:
        params["projectKeyOrId"] = project_key
    code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params=params)
    if code != 200 or not data:
        return code, [], f"ボード一覧取得に失敗: {err}"
    boards.extend(data.get("values", []))
    start_at = data.get("startAt", 0)
    max_results = data.get("maxResults", 50)
    total = data.get("total", len(boards))
    while start_at + max_results < total:
        start_at += max_results
        params_page = dict(params)
        params_page["startAt"] = start_at
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params=params_page)
        if code != 200 or not data:
            return code, boards, f"ボード一覧のページング取得に失敗: {err}"
        boards.extend(data.get("values", []))
    return 200, boards, ""


def resolve_board(JIRA_DOMAIN: str, auth: HTTPBasicAuth) -> Tuple[int, Optional[Dict[str, Any]], str]:
    board_id_env = os.getenv("JIRA_BOARD_ID")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    # 1) 指定が数値IDの場合
    if board_id_env and board_id_env.isdigit():
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id_env}", auth)
        if code == 200 and data:
            return 200, data, ""
        return code, None, f"ボードID {board_id_env} の取得に失敗: {err}"

    # 2) 指定が名称の場合
    if board_id_env and not board_id_env.isdigit():
        code, boards, err = list_scrum_boards(JIRA_DOMAIN, auth, project_key)
        if code != 200:
            return code, None, err
        # exact -> partial
        exact = [b for b in boards if str(b.get("name", "")).lower() == board_id_env.lower()]
        if exact:
            return 200, exact[0], ""
        partial = [b for b in boards if board_id_env.lower() in str(b.get("name", "")).lower()]
        if partial:
            return 200, partial[0], ""
        # 全体から再探索
        code2, boards2, err2 = list_scrum_boards(JIRA_DOMAIN, auth, None)
        if code2 != 200:
            return code2, None, err2
        exact = [b for b in boards2 if str(b.get("name", "")).lower() == board_id_env.lower()]
        if exact:
            return 200, exact[0], ""
        partial = [b for b in boards2 if board_id_env.lower() in str(b.get("name", "")).lower()]
        if partial:
            return 200, partial[0], ""
        return 404, None, f"ボード名 '{board_id_env}' は見つかりませんでした"

    # 3) 指定がない場合: プロジェクト配下のボードを優先し、単一なら採用。複数なら先頭を採用。
    code, boards, err = list_scrum_boards(JIRA_DOMAIN, auth, project_key)
    if code != 200:
        return code, None, err
    if boards:
        return 200, boards[0], ""
    # 4) 全体からの候補
    code2, boards2, err2 = list_scrum_boards(JIRA_DOMAIN, auth, None)
    if code2 != 200:
        return code2, None, err2
    if boards2:
        return 200, boards2[0], ""
    return 404, None, "Scrumボードが見つかりませんでした"


def resolve_active_sprint(JIRA_DOMAIN: str, auth: HTTPBasicAuth, board_id: int) -> Tuple[int, Optional[Dict[str, Any]], str]:
    sprint_id_env = os.getenv("JIRA_SPRINT_ID")
    if sprint_id_env:
        code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/sprint/{sprint_id_env}", auth)
        if code == 200 and data:
            return 200, data, ""
        return code, None, f"スプリントID {sprint_id_env} の取得に失敗: {err}"

    params = {"state": "active", "maxResults": 50}
    code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}/sprint", auth, params=params)
    if code != 200 or not data:
        return code, None, f"アクティブスプリントの取得に失敗: {err}"

    sprints = data.get("values", [])
    if not sprints:
        return 404, None, "アクティブなスプリントが見つかりません"
    # 複数あっても先頭を採用（PoCの自動化方針）
    return 200, sprints[0], ""


def count_issues_in_sprint(JIRA_DOMAIN: str, auth: HTTPBasicAuth, sprint_id: int, project_key: Optional[str]) -> Tuple[int, Optional[int], str]:
    jql = f"sprint={sprint_id}"
    if project_key:
        jql = f"project={project_key} AND {jql}"

    # 件数取得専用エンドポイント: POST /rest/api/3/search/approximate-count
    try:
        resp = requests.post(
            f"{JIRA_DOMAIN}/rest/api/3/search/approximate-count",
            json={"jql": jql},
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as e:
        return 0, None, f"HTTPリクエストエラー: {e}"

    if resp.status_code == 200:
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return 200, None, "レスポンスのJSON解析に失敗しました"
        count = data.get("count")
        if isinstance(count, int):
            return 200, count, ""
        return 200, None, f"想定外のレスポンス: {data}"

    return resp.status_code, None, f"POST(count) {resp.status_code} {resp.text}"


def count_issues_in_open_sprints(JIRA_DOMAIN: str, auth: HTTPBasicAuth, project_key: Optional[str]) -> Tuple[int, Optional[int], str]:
    # プロジェクトに紐づく全アクティブスプリントの課題数を概算で取得
    if project_key:
        jql = f"project={project_key} AND sprint in openSprints()"
    else:
        jql = "sprint in openSprints()"

    try:
        resp = requests.post(
            f"{JIRA_DOMAIN}/rest/api/3/search/approximate-count",
            json={"jql": jql},
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as e:
        return 0, None, f"HTTPリクエストエラー: {e}"

    if resp.status_code == 200:
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return 200, None, "レスポンスのJSON解析に失敗しました"
        count = data.get("count")
        if isinstance(count, int):
            return 200, count, ""
        return 200, None, f"想定外のレスポンス: {data}"

    return resp.status_code, None, f"POST(count openSprints) {resp.status_code} {resp.text}"


def main() -> int:
    maybe_load_dotenv()
    JIRA_DOMAIN = load_env("JIRA_DOMAIN").rstrip("/")
    email = load_env("JIRA_EMAIL")
    api_token = load_env("JIRA_API_TOKEN")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    auth = HTTPBasicAuth(email, api_token)

    code, board, err = resolve_board(JIRA_DOMAIN, auth)
    if code != 200 or not board:
        # フォールバック: ボードがない/見つからない場合は openSprints() で件数だけ返す
        code2, total2, err2 = count_issues_in_open_sprints(JIRA_DOMAIN, auth, project_key)
        if code2 == 200 and total2 is not None:
            print(f"プロジェクト '{project_key or '-'}' のアクティブスプリント(全ボード)のタスク総数: {total2}")
            return 0
        print(err, file=sys.stderr)
        return 1

    board_id = int(board.get("id"))
    board_name = board.get("name")

    code, sprint, err = resolve_active_sprint(JIRA_DOMAIN, auth, board_id)
    if code != 200 or not sprint:
        # フォールバック: アクティブスプリントがない場合
        code2, total2, err2 = count_issues_in_open_sprints(JIRA_DOMAIN, auth, project_key)
        if code2 == 200 and total2 is not None:
            print(f"プロジェクト '{project_key or '-'}' のアクティブスプリント(全ボード)のタスク総数: {total2}")
            return 0
        print(err, file=sys.stderr)
        return 1

    sprint_id = int(sprint.get("id"))
    sprint_name = sprint.get("name")

    # ボードからプロジェクトキー推測
    if not project_key:
        loc = (board or {}).get("location") or {}
        pkey = loc.get("projectKey")
        if pkey:
            project_key = str(pkey)

    code, total, err = count_issues_in_sprint(JIRA_DOMAIN, auth, sprint_id, project_key)
    if code != 200 or total is None:
        print(err, file=sys.stderr)
        return 1

    print(f"ボード '{board_name}' のアクティブスプリント '{sprint_name}' のタスク総数: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
