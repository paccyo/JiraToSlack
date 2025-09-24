import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List

import requests
from requests.auth import HTTPBasicAuth


def required_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        print(f"環境変数が未設定です: {key}", file=sys.stderr)
        sys.exit(2)
    return v


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


def main() -> int:
    maybe_load_dotenv()
    domain = required_env("JIRA_DOMAIN").rstrip("/")
    email = required_env("JIRA_EMAIL")
    token = required_env("JIRA_API_TOKEN")
    board_id = os.getenv("JIRA_BOARD_ID")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    auth = HTTPBasicAuth(email, token)

    if not board_id:
        params = {"maxResults": 50}
        if project_key:
            params["projectKeyOrId"] = project_key
        r = requests.get(f"{domain}/rest/agile/1.0/board", params=params, auth=auth, timeout=30)
        if r.status_code != 200:
            print(f"ボード一覧取得失敗: {r.status_code} {r.text}", file=sys.stderr)
            return 1
        d = r.json()
        vals: List[Dict[str, Any]] = d.get("values", []) if isinstance(d, dict) else []
        if not vals:
            print("ボードが見つかりません", file=sys.stderr)
            return 1
        board_id = str(vals[0].get("id"))

    out: List[Dict[str, Any]] = []
    start = 0
    while True:
        r2 = requests.get(
            f"{domain}/rest/agile/1.0/board/{board_id}/sprint",
            params={"maxResults": 50, "startAt": start, "state": "active,closed"},
            auth=auth,
            timeout=30,
        )
        if r2.status_code != 200:
            print(f"スプリント一覧取得失敗: {r2.status_code} {r2.text}", file=sys.stderr)
            return 1
        d2 = r2.json()
        vals2: List[Dict[str, Any]] = d2.get("values", []) if isinstance(d2, dict) else []
        if not vals2:
            break
        out.extend([{"id": v.get("id"), "name": v.get("name"), "state": v.get("state")} for v in vals2])
        if len(vals2) < 50:
            break
        start += len(vals2)

    print(json.dumps({"boardId": int(board_id), "sprints": out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
