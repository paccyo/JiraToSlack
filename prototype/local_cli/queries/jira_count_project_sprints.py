import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth

from prototype.local_cli.lib.board_selector import resolve_board_with_preferences


def maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir.parent / ".env",  # .../prototype/local_cli/.env
        script_dir / ".env",          # .../prototype/local_cli/queries/.env
        Path.cwd() / ".env",          # current working dir
        Path(__file__).resolve().parents[2] / ".env",  # repo root (best-effort)
    ]
    for p in candidates:
        try:
            if p.exists():
                load_dotenv(p, override=False)
        except Exception:
            pass


def required_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        print(f"環境変数が未設定です: {key}", file=sys.stderr)
        sys.exit(2)
    return v


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


def resolve_board(domain: str, auth: HTTPBasicAuth) -> Tuple[int, Optional[Dict[str, Any]], str]:
    clean_domain = (domain or "").rstrip("/")
    if not clean_domain:
        return 400, None, "JIRA_DOMAIN が未設定です"

    board_id = os.getenv("JIRA_BOARD_ID")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    def fetch(url: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Optional[Dict[str, Any]], str]:
        return api_get(url, auth, params=params)

    return resolve_board_with_preferences(clean_domain, fetch, project_key, board_id, context="jira_count_project_sprints.resolve_board")


def list_all_sprints(domain: str, auth: HTTPBasicAuth, board_id: int, states: Optional[List[str]] = None) -> Tuple[int, List[Dict[str, Any]], str]:
    states = states or ["active", "future", "closed"]
    all_sprints: List[Dict[str, Any]] = []
    for st in states:
        start_at = 0
        while True:
            code, data, err = api_get(
                f"{domain}/rest/agile/1.0/board/{board_id}/sprint",
                auth,
                params={"state": st, "startAt": start_at, "maxResults": 50},
            )
            if code != 200 or not data:
                return code, [], f"スプリント一覧取得失敗: {err}"
            vals = data.get("values", [])
            total = int(data.get("total", len(vals)))
            all_sprints.extend(vals)
            start_at += len(vals)
            if start_at >= total or not vals:
                break
    return 200, all_sprints, ""


def main() -> int:
    maybe_load_dotenv()
    domain = required_env("JIRA_DOMAIN").rstrip("/")
    email = required_env("JIRA_EMAIL")
    token = required_env("JIRA_API_TOKEN")
    auth = HTTPBasicAuth(email, token)

    code_b, board, err_b = resolve_board(domain, auth)
    if code_b != 200 or not board:
        print(err_b, file=sys.stderr)
        return 1
    bid = int(board.get("id"))

    code_s, sprints, err_s = list_all_sprints(domain, auth, bid)
    if code_s != 200:
        print(err_s, file=sys.stderr)
        return 1

    total = len(sprints)
    by_state = {"active": 0, "future": 0, "closed": 0}
    for sp in sprints:
        st = str(sp.get("state", "")).lower()
        if st in by_state:
            by_state[st] += 1
        else:
            by_state[st] = by_state.get(st, 0) + 1

    payload = {
        "board": {"id": bid, "name": board.get("name")},
        "total": total,
        "byState": by_state,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
