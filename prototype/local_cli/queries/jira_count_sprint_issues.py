import os
import sys
import json
from typing import Any, Dict

import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path


def required_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        print(f"環境変数が未設定です: {key}", file=sys.stderr)
        sys.exit(2)
    return v


def maybe_load_dotenv() -> None:
    """Load .env with priority to prototype/local_cli/.env.

    Search order:
    1) prototype/local_cli/.env
    2) prototype/local_cli/queries/.env
    3) current working directory .env
    4) repository root .env (best-effort)
    """
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
            # ignore individual load failures and continue
            pass


def main() -> int:
    maybe_load_dotenv()
    domain = required_env("JIRA_DOMAIN").rstrip("/")
    email = required_env("JIRA_EMAIL")
    token = required_env("JIRA_API_TOKEN")
    board_id = os.getenv("JIRA_BOARD_ID")
    sprint_id = os.getenv("JIRA_SPRINT_ID")

    auth = HTTPBasicAuth(email, token)

    if not sprint_id:
        if not board_id:
            # Try to resolve a board automatically (prefer project-scoped board)
            params = {"maxResults": 50}
            proj = os.getenv("JIRA_PROJECT_KEY")
            if proj:
                params["projectKeyOrId"] = proj
            try:
                resp_b = requests.get(f"{domain}/rest/agile/1.0/board", params=params, auth=auth, timeout=30)
            except requests.RequestException as e:
                print(f"ボード取得失敗: {e}", file=sys.stderr)
                return 1
            if resp_b.status_code != 200:
                print(f"ボード一覧取得失敗: {resp_b.status_code} {resp_b.text}", file=sys.stderr)
                return 1
            data_b = resp_b.json() if isinstance(resp_b.json(), dict) else {}
            values = data_b.get("values", []) if isinstance(data_b, dict) else []
            if not values:
                print("ボードが見つかりません", file=sys.stderr)
                return 1
            board_id = str(values[0].get("id"))
        # resolve active sprint
        resp = requests.get(f"{domain}/rest/agile/1.0/board/{board_id}/sprint", params={"state": "active", "maxResults": 50}, auth=auth, timeout=30)
        if resp.status_code != 200:
            print(f"スプリント一覧取得失敗: {resp.status_code} {resp.text}", file=sys.stderr)
            return 1
        data = resp.json()
        vals = data.get("values", []) if isinstance(data, dict) else []
        if not vals:
            print("アクティブスプリントが見つかりません", file=sys.stderr)
            return 1
        sprint_id = str(vals[0].get("id"))

    r = requests.get(
        f"{domain}/rest/agile/1.0/sprint/{sprint_id}/issue",
        params={"maxResults": 0},
        auth=auth,
        timeout=30,
    )
    if r.status_code != 200:
        print(f"スプリント課題数取得失敗: {r.status_code} {r.text}", file=sys.stderr)
        return 1
    data2: Dict[str, Any] = r.json()
    total = int(data2.get("total", 0))
    print(json.dumps({"sprintId": int(sprint_id), "total": total}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
