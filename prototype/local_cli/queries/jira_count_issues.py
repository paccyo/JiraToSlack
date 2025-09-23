import os
import sys
import json
from typing import Any, Dict
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth


def maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    for p in [Path(__file__).resolve().parent / ".env", Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)


def required_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print(f"環境変数が未設定です: {key}", file=sys.stderr)
        sys.exit(2)
    return val


def main() -> int:
    maybe_load_dotenv()
    domain = required_env("JIRA_DOMAIN").rstrip("/")
    email = required_env("JIRA_EMAIL")
    token = required_env("JIRA_API_TOKEN")
    jql = os.getenv("JQL") or required_env("JQL")

    auth = HTTPBasicAuth(email, token)
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
    print(json.dumps({"total": total}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
