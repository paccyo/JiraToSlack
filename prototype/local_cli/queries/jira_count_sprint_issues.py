import os
import sys
import json
from typing import Any, Dict

import requests
from requests.auth import HTTPBasicAuth


def required_env(key: str) -> str:
    v = os.getenv(key)
    if not v:
        print(f"環境変数が未設定です: {key}", file=sys.stderr)
        sys.exit(2)
    return v


def main() -> int:
    domain = required_env("JIRA_DOMAIN").rstrip("/")
    email = required_env("JIRA_EMAIL")
    token = required_env("JIRA_API_TOKEN")
    board_id = os.getenv("JIRA_BOARD_ID")
    sprint_id = os.getenv("JIRA_SPRINT_ID")

    auth = HTTPBasicAuth(email, token)

    if not sprint_id:
        if not board_id:
            print("JIRA_SPRINT_ID または JIRA_BOARD_ID が必要です", file=sys.stderr)
            return 2
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
