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

    # 1) スクリプト直下の .env（最優先）
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / ".env",
        Path.cwd() / ".env",  # 実行ディレクトリ
        Path(__file__).resolve().parents[2] / ".env",  # リポジトリルート想定
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=False)


def api_get(url: str, auth: HTTPBasicAuth, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Optional[Dict[str, Any]], str]:
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


def resolve_board_by_name(
    JIRA_DOMAIN: str, auth: HTTPBasicAuth, name: str, project_key: Optional[str]
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    # プロジェクト配下のScrumボードを優先、なければ全体から部分一致で探索
    boards: List[Dict[str, Any]] = []
    params: Dict[str, Any] = {"type": "scrum", "maxResults": 50}
    if project_key:
        params["projectKeyOrId"] = project_key
    code, data, err = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params=params)
    if code == 200 and data:
        boards.extend(data.get("values", []))
    else:
        return code, None, f"ボード一覧取得に失敗: {err}"

    exact = [b for b in boards if str(b.get("name", "")).lower() == name.lower()]
    if exact:
        return 200, exact[0], ""
    partial = [b for b in boards if name.lower() in str(b.get("name", "")).lower()]
    if partial:
        return 200, partial[0], ""

    # 全体から再探索
    code2, data2, err2 = api_get(
        f"{JIRA_DOMAIN}/rest/agile/1.0/board", auth, params={"type": "scrum", "maxResults": 50}
    )
    if code2 != 200 or not data2:
        return code2, None, f"ボード一覧取得に失敗: {err2}"
    boards2 = data2.get("values", [])
    exact = [b for b in boards2 if str(b.get("name", "")).lower() == name.lower()]
    if exact:
        return 200, exact[0], ""
    partial = [b for b in boards2 if name.lower() in str(b.get("name", "")).lower()]
    if partial:
        return 200, partial[0], ""
    return 404, None, f"ボード名 '{name}' は見つかりませんでした"


def try_infer_project_key_from_board(JIRA_DOMAIN: str, auth: HTTPBasicAuth, board: Dict[str, Any]) -> Optional[str]:
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


def main() -> int:
    maybe_load_dotenv()
    JIRA_DOMAIN = load_env("JIRA_DOMAIN").rstrip("/")
    email = load_env("JIRA_EMAIL")
    api_token = load_env("JIRA_API_TOKEN")
    project_key = os.getenv("JIRA_PROJECT_KEY")
    jql_override = os.getenv("JIRA_JQL")
    filter_id = os.getenv("JIRA_FILTER_ID")
    board_id_env = os.getenv("JIRA_BOARD_ID")

    auth = HTTPBasicAuth(email, api_token)

    # 1) JQL優先
    if jql_override:
        jql = jql_override
    # 2) フィルターIDからJQL
    elif filter_id:
        code_f, data_f, err_f = api_get(f"{JIRA_DOMAIN}/rest/api/3/filter/{filter_id}", auth)
        if code_f == 200 and data_f:
            jql_val = data_f.get("jql")
            if isinstance(jql_val, str) and jql_val.strip():
                jql = jql_val
            else:
                print(f"フィルター {filter_id} のJQLが取得できませんでした", file=sys.stderr)
                return 1
        else:
            print(f"フィルター取得に失敗: {err_f}", file=sys.stderr)
            return 1
    else:
        # 3) プロジェクトキーを推測
        inferred_project: Optional[str] = project_key
        if not inferred_project and board_id_env:
            # ボードから推測（数値ID or 名称）
            if board_id_env.isdigit():
                code_b, data_b, err_b = api_get(f"{JIRA_DOMAIN}/rest/agile/1.0/board/{board_id_env}", auth)
                if code_b == 200 and data_b:
                    inferred_project = try_infer_project_key_from_board(JIRA_DOMAIN, auth, data_b)
                else:
                    print(f"ボードID {board_id_env} の取得に失敗: {err_b}", file=sys.stderr)
                    return 1
            else:
                code_b, data_b, err_b = resolve_board_by_name(JIRA_DOMAIN, auth, board_id_env, project_key)
                if code_b == 200 and data_b:
                    inferred_project = try_infer_project_key_from_board(JIRA_DOMAIN, auth, data_b)
                else:
                    print(f"ボード名 '{board_id_env}' の解決に失敗: {err_b}", file=sys.stderr)
                    return 1

        if not inferred_project:
            # 最近のプロジェクトから最も最近の1件を採用
            code_p, data_p, err_p = api_get(f"{JIRA_DOMAIN}/rest/api/3/project/recent", auth)
            if code_p == 200 and isinstance(data_p, list) and data_p:
                inferred_project = str((data_p[0] or {}).get("key"))
            else:
                # 全プロジェクト一覧から1件選択
                code_p2, data_p2, err_p2 = api_get(
                    f"{JIRA_DOMAIN}/rest/api/3/project/search", auth, params={"maxResults": 50}
                )
                if code_p2 == 200 and data_p2 and isinstance(data_p2.get("values"), list) and data_p2.get("values"):
                    inferred_project = str((data_p2.get("values")[0] or {}).get("key"))
                else:
                    print("プロジェクトの自動推測に失敗しました。JIRA_PROJECT_KEY を設定してください。", file=sys.stderr)
                    return 1

        project_key = inferred_project
        jql = f"project={project_key}"

    # 件数取得専用エンドポイント: POST /rest/api/3/search/approximate-count
    url_count = f"{JIRA_DOMAIN}/rest/api/3/search/approximate-count"
    try:
        resp = requests.post(
            url_count,
            json={"jql": jql},
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as e:
        print(f"HTTPリクエストエラー: {e}", file=sys.stderr)
        return 1

    if resp.status_code == 200:
        try:
            data = resp.json()
        except json.JSONDecodeError:
            print("レスポンスのJSON解析に失敗しました", file=sys.stderr)
            return 1
        count = data.get("count")
        if isinstance(count, int):
            print(f"プロジェクト {project_key} のタスク総数: {count}")
            return 0
        else:
            print(f"想定外のレスポンス: {data}", file=sys.stderr)
            return 1

    # 参考情報（詳細は stderr に出力）
    print(
        "Error: POST /rest/api/3/search/approximate-count 失敗:",
        f"{resp.status_code} {resp.text}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
