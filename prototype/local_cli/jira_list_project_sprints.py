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


def list_boards(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth, project_key: Optional[str], board_type: Optional[str] = None
) -> Tuple[int, List[Dict[str, Any]], str]:
    boards: List[Dict[str, Any]] = []
    params: Dict[str, Any] = {"maxResults": 50}
    if board_type:
        params["type"] = board_type
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


def list_all_boards(JIRA_DOMAIN: str, auth: HTTPBasicAuth) -> Tuple[int, List[Dict[str, Any]], str]:
    return list_boards(JIRA_DOMAIN, auth, project_key=None, board_type=None)


def resolve_board_by_name(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth, name: str, project_key: Optional[str]
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    # まずプロジェクト配下のボードで探索、見つからなければ全ボード
    boards: List[Dict[str, Any]] = []
    if project_key:
        code, boards, err = list_boards(JIRA_DOMAIN, auth, project_key, board_type=None)
        if code != 200:
            return code, None, err
    else:
        code, boards, err = list_all_boards(JIRA_DOMAIN, auth)
        if code != 200:
            return code, None, err

    matches = [b for b in boards if str(b.get("name", "")).lower() == name.lower()]
    if not matches:
        # 部分一致で再トライ
        partial = [b for b in boards if name.lower() in str(b.get("name", "")).lower()]
        if len(partial) == 1:
            return 200, partial[0], ""
        if len(partial) > 1:
            cand = ", ".join([f"{b.get('name')} (id={b.get('id')})" for b in partial[:10]])
            return 409, None, f"ボード名 '{name}' の候補が複数見つかりました: {cand}"
        return 404, None, f"ボード名 '{name}' は見つかりませんでした"
    if len(matches) > 1:
        cand = ", ".join([f"{b.get('name')} (id={b.get('id')})" for b in matches[:10]])
        return 409, None, f"ボード名 '{name}' の候補が複数見つかりました: {cand}"
    return 200, matches[0], ""


def list_board_sprints(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth, board_id: int, state: Optional[str]
) -> Tuple[int, List[Dict[str, Any]], str]:
    sprints: List[Dict[str, Any]] = []
    params: Dict[str, Any] = {"maxResults": 50}
    if state:
        params["state"] = state

    code, data, err = api_get(
        f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}/sprint", auth, params=params
    )
    if code != 200 or not data:
        return code, [], f"ボード {board_id} のスプリント取得に失敗: {err}"

    sprints.extend(data.get("values", []))
    start_at = data.get("startAt", 0)
    max_results = data.get("maxResults", 50)
    total = data.get("total", len(sprints))

    while start_at + max_results < total:
        start_at += max_results
        params_page = dict(params)
        params_page["startAt"] = start_at
        code, data, err = api_get(
            f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}/sprint", auth, params=params_page
        )
        if code != 200 or not data:
            return code, sprints, f"ボード {board_id} のスプリントページング取得に失敗: {err}"
        sprints.extend(data.get("values", []))

    return 200, sprints, ""


def get_board_detail(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth, board_id: int
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    return api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id}", auth)


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
    code, detail, _ = get_board_detail(JIRA_DOMAIN, auth, bid_int)
    if code == 200 and detail:
        loc = (detail or {}).get("location") or {}
        pkey = loc.get("projectKey")
        if pkey:
            return str(pkey)
    return None


def main() -> int:
    maybe_load_dotenv()
    JIRA_DOMAIN = load_env("JIRA_DOMAIN").rstrip("/")
    email = load_env("JIRA_EMAIL")
    api_token = load_env("JIRA_API_TOKEN")
    project_key = os.getenv("JIRA_PROJECT_KEY")
    board_id_env = os.getenv("JIRA_BOARD_ID")
    state = os.getenv("JIRA_SPRINT_STATE")  # 例: active, future, closed（カンマ区切り不可、1つ）

    auth = HTTPBasicAuth(email, api_token)

    boards: List[Dict[str, Any]] = []
    resolved_board: Optional[Dict[str, Any]] = None

    # 0) URLが .env の JIRA_DOMAIN/JIRA_DOMAIN 等から推測できる場合はそれを使う（将来拡張の余地）
    # 現状は未実装、envの JIRA_BOARD_ID/JIRA_PROJECT_KEY を優先

    # 1) 環境変数がある場合: 数値ID or 名前で解決
    if board_id_env:
        if board_id_env.isdigit():
            code_b, data_b, err_b = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id_env}", auth)
            if code_b == 200 and data_b:
                resolved_board = data_b
            else:
                print(f"ボードID {board_id_env} の取得に失敗: {err_b}", file=sys.stderr)
                return 1
        else:
            code_b, data_b, err_b = resolve_board_by_name(JIRA_DOMAIN, auth, board_id_env, project_key)
            if code_b == 200 and data_b:
                resolved_board = data_b
            else:
                print(f"ボード名 '{board_id_env}' の解決に失敗: {err_b}", file=sys.stderr)
                return 1

    # 2) なければプロジェクト配下のScrumボードを列挙し、単一なら自動選択
    if not resolved_board:
        # プロジェクト配下のすべてのボードから検索（Scrum限定しない）
        code_b, boards, err_b = list_boards(JIRA_DOMAIN, auth, project_key, board_type=None)
        if code_b != 200:
            print(err_b, file=sys.stderr)
            return 1
        # そのまま採用（PoC: 自動選択）
        if boards:
            resolved_board = boards[0]

    # 3) 依然として見つからない場合は全Scrumボードを走査し、単一候補なら採用
    if not resolved_board:
        code_b2, boards2, err_b2 = list_all_boards(JIRA_DOMAIN, auth)
        if code_b2 != 200:
            print(err_b2, file=sys.stderr)
            return 1
        if boards2:
            resolved_board = boards2[0]

    if not resolved_board:
        print(
            f"プロジェクト '{project_key or '-'}' に紐づくScrumボードが見つかりません。"
            "JIRA_BOARD_ID を設定するか、JIRA_PROJECT_KEY の見直しをご検討ください。"
        )
        return 0

    # 以降は解決した（または自動選択した）ボードでスプリント取得
    boards = [resolved_board]
    print(f"使用ボード: {resolved_board.get('name')} (id={resolved_board.get('id')})")
    if not project_key:
        inferred = try_infer_project_key_from_board(JIRA_DOMAIN, auth, resolved_board)
        if inferred:
            project_key = inferred
            print(f"推測したプロジェクトキー: {project_key}\n")
        else:
            print("プロジェクトキーを推測できませんでした。必要なら JIRA_PROJECT_KEY を設定してください。\n")

    for b in boards:
        bid = b.get("id")
        bname = b.get("name")
        print(f"ボード: {bname} (id={bid})")

        code_s, sprints, err_s = list_board_sprints(JIRA_DOMAIN, auth, int(bid), state)
        if code_s != 200:
            print(err_s, file=sys.stderr)
            continue

        if not sprints:
            print("  スプリントは見つかりませんでした。\n")
            continue

        for s in sprints:
            sid = s.get("id")
            sname = s.get("name")
            sstate = s.get("state")
            start_date = s.get("startDate")
            end_date = s.get("endDate")
            complete_date = s.get("completeDate")
            print(
                f"  - {sname} (id={sid}, state={sstate}, start={start_date}, end={end_date}, complete={complete_date})"
            )
        print("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
