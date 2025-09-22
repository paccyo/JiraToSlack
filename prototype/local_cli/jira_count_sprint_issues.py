import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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


def resolve_board(jira_base_url: str, auth: HTTPBasicAuth) -> Tuple[int, Optional[Dict[str, Any]], str]:
    board_id = os.getenv("JIRA_BOARD_ID")
    if board_id:
        code, data, err = api_get(f"{jira_base_url}/rest/agile/1.0/board/{board_id}", auth)
        if code == 200 and data:
            return 200, data, ""
        return code, None, f"ボードID {board_id} の取得に失敗: {err}"

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


def resolve_active_sprint(jira_base_url: str, auth: HTTPBasicAuth, board_id: int) -> Tuple[int, Optional[Dict[str, Any]], str]:
    sprint_id_env = os.getenv("JIRA_SPRINT_ID")
    if sprint_id_env:
        code, data, err = api_get(f"{jira_base_url}/rest/agile/1.0/sprint/{sprint_id_env}", auth)
        if code == 200 and data:
            return 200, data, ""
        return code, None, f"スプリントID {sprint_id_env} の取得に失敗: {err}"

    params = {"state": "active", "maxResults": 50}
    code, data, err = api_get(f"{jira_base_url}/rest/agile/1.0/board/{board_id}/sprint", auth, params=params)
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


def count_issues_in_sprint(jira_base_url: str, auth: HTTPBasicAuth, sprint_id: int, project_key: Optional[str]) -> Tuple[int, Optional[int], str]:
    jql = f"sprint={sprint_id}"
    if project_key:
        jql = f"project={project_key} AND {jql}"

    # 件数取得専用エンドポイント: POST /rest/api/3/search/approximate-count
    try:
        resp = requests.post(
            f"{jira_base_url}/rest/api/3/search/approximate-count",
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


def count_issues_in_open_sprints(jira_base_url: str, auth: HTTPBasicAuth, project_key: Optional[str]) -> Tuple[int, Optional[int], str]:
    # プロジェクトに紐づく全アクティブスプリントの課題数を概算で取得
    if project_key:
        jql = f"project={project_key} AND sprint in openSprints()"
    else:
        jql = "sprint in openSprints()"

    try:
        resp = requests.post(
            f"{jira_base_url}/rest/api/3/search/approximate-count",
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
    jira_base_url = load_env("JIRA_BASE_URL").rstrip("/")
    email = load_env("JIRA_EMAIL")
    api_token = load_env("JIRA_API_TOKEN")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    auth = HTTPBasicAuth(email, api_token)

    code, board, err = resolve_board(jira_base_url, auth)
    if code != 200 or not board:
        # フォールバック: ボードがない/見つからない場合は openSprints() で件数だけ返す
        code2, total2, err2 = count_issues_in_open_sprints(jira_base_url, auth, project_key)
        if code2 == 200 and total2 is not None:
            print(f"プロジェクト '{project_key or '-'}' のアクティブスプリント(全ボード)のタスク総数: {total2}")
            return 0
        print(err, file=sys.stderr)
        return 1

    board_id = int(board.get("id"))
    board_name = board.get("name")

    code, sprint, err = resolve_active_sprint(jira_base_url, auth, board_id)
    if code != 200 or not sprint:
        # フォールバック: アクティブスプリントがない場合
        code2, total2, err2 = count_issues_in_open_sprints(jira_base_url, auth, project_key)
        if code2 == 200 and total2 is not None:
            print(f"プロジェクト '{project_key or '-'}' のアクティブスプリント(全ボード)のタスク総数: {total2}")
            return 0
        print(err, file=sys.stderr)
        return 1

    sprint_id = int(sprint.get("id"))
    sprint_name = sprint.get("name")

    code, total, err = count_issues_in_sprint(jira_base_url, auth, sprint_id, project_key)
    if code != 200 or total is None:
        print(err, file=sys.stderr)
        return 1

    print(f"ボード '{board_name}' のアクティブスプリント '{sprint_name}' のタスク総数: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
