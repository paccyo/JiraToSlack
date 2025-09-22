import os
import sys
import json
from pathlib import Path
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


def main() -> int:
    maybe_load_dotenv()
    jira_base_url = load_env("JIRA_BASE_URL").rstrip("/")
    email = load_env("JIRA_EMAIL")
    api_token = load_env("JIRA_API_TOKEN")
    project_key = os.getenv("JIRA_PROJECT_KEY")

    if not project_key:
        print("環境変数 JIRA_PROJECT_KEY が未設定です。全プロジェクト件数の取得は非対応です。", file=sys.stderr)
        return 2

    jql = f"project={project_key}"

    # 件数取得専用エンドポイント: POST /rest/api/3/search/approximate-count
    url_count = f"{jira_base_url}/rest/api/3/search/approximate-count"
    try:
        resp = requests.post(
            url_count,
            json={"jql": jql},
            auth=HTTPBasicAuth(email, api_token),
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
