import os
import sys
import json
import argparse
from typing import Any, Dict, Optional
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth


def maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir.parent / ".env",  # prototype/local_cli/.env
        script_dir / ".env",         # queries/.env (fallback)
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=False)


def api_get(url: str, auth: HTTPBasicAuth, params: Optional[Dict[str, Any]] = None) -> tuple[int, Optional[Dict[str, Any]], str]:
    try:
        r = requests.get(url, params=params, auth=auth, headers={"Accept": "application/json"}, timeout=30)
    except requests.RequestException as e:
        return 0, None, f"HTTPエラー: {e}"
    if r.status_code == 200:
        try:
            return 200, r.json(), ""
        except Exception:
            return 200, None, "JSON解析失敗"
    return r.status_code, None, r.text


def required_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print(f"環境変数が未設定です: {key}", file=sys.stderr)
        sys.exit(2)
    return val


def main() -> int:
    maybe_load_dotenv()
    parser = argparse.ArgumentParser(description="Jira課題数をカウントします")
    parser.add_argument("--jql", help="JQL を直接指定")
    parser.add_argument("--scope", choices=["sprint", "project"], help="簡易JQLのスコープ")
    parser.add_argument("--project", help="scope=project のときのプロジェクトキー。未指定時は JIRA_PROJECT_KEY を使用")
    args = parser.parse_args()

    domain = required_env("JIRA_DOMAIN").rstrip("/")
    email = required_env("JIRA_EMAIL")
    token = required_env("JIRA_API_TOKEN")
    auth = HTTPBasicAuth(email, token)

    # 1) 優先: 明示 --jql
    jql: Optional[str] = args.jql or os.getenv("JQL")

    # 2) 無指定なら scope に従って自動生成（デフォルトは sprint）
    scope = args.scope or os.getenv("COUNT_SCOPE") or ("sprint" if not jql else None)
    if not jql and scope == "project":
        project = args.project or os.getenv("JIRA_PROJECT_KEY")
        if not project:
            print("project スコープには --project もしくは JIRA_PROJECT_KEY が必要です", file=sys.stderr)
            return 2
        jql = f"project={project}"
    if not jql and scope == "sprint":
        sprint_id = os.getenv("JIRA_SPRINT_ID")
        board_id = os.getenv("JIRA_BOARD_ID")
        # resolve sprint id if needed
        if not sprint_id:
            # まずボードIDが無ければ取得
            params = {"maxResults": 50}
            pj = os.getenv("JIRA_PROJECT_KEY")
            if pj:
                params["projectKeyOrId"] = pj
            code_b, data_b, err_b = api_get(f"{domain}/rest/agile/1.0/board", auth, params)
            if code_b != 200 or not data_b or not (data_b.get("values") or []):
                print(f"ボード取得失敗: {err_b or code_b}", file=sys.stderr)
                return 1
            board_id = str((data_b.get("values") or [])[0].get("id"))
            # アクティブスプリント
            code_s, data_s, err_s = api_get(f"{domain}/rest/agile/1.0/board/{board_id}/sprint", auth, {"state": "active", "maxResults": 50})
            if code_s != 200 or not data_s or not (data_s.get("values") or []):
                print(f"アクティブスプリントが見つかりません", file=sys.stderr)
                return 1
            sprint_id = str((data_s.get("values") or [])[0].get("id"))
        jql = f"Sprint={sprint_id}"

    if not jql:
        print("JQL が未指定です。--jql を与えるか、--scope (sprint|project) で自動生成してください。", file=sys.stderr)
        return 2

    url = f"{domain}/rest/api/3/search"
    try:
        r = requests.get(url, params={"jql": jql, "maxResults": 0}, auth=auth, headers={"Accept": "application/json"}, timeout=30)
    except requests.RequestException as e:
        print(f"HTTPリクエストエラー: {e}", file=sys.stderr)
        return 1

    if r.status_code != 200:
        print(f"Jira検索失敗: {r.status_code} {r.text}", file=sys.stderr)
        return 1

    try:
        data: Dict[str, Any] = r.json()
    except Exception:
        print("JSON解析失敗", file=sys.stderr)
        return 1

    total = int(data.get("total", 0))
    print(json.dumps({"total": total, "jql": jql}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
