import os
from jira import JIRA
from dotenv import load_dotenv
load_dotenv()

# --- 設定項目 ---
# ご自身のJira環境に合わせて書き換えてください

# 1. JiraサーバーのURL (例: https://your-domain.atlassian.net)
# JIRA_SERVER = "https://your-domain.atlassian.net"
JIRA_SERVER = os.getenv("JIRA_DOMAIN")

# 2. Jiraに登録しているメールアドレス
# JIRA_EMAIL = "your.email@example.com"
JIRA_EMAIL = os.getenv("JIRA_EMAIL")

# 3. 事前に取得したAPIトークン
# JIRA_API_TOKEN = "YOUR_API_TOKEN"
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

# 4. 実行したいJQLクエリ
# 例: 自分に割り当てられていて、未完了の課題を優先度順に並べる
JQL_QUERY = 'status != Done ORDER BY priority DESC'


# --- ここからが処理の本体 ---

def search_jira_issues(server, email, token, jql):
    """Jiraに接続し、指定されたJQLで課題を検索する"""
    
    print("Jiraサーバーに接続しています...")
    try:
        # メールアドレスとAPIトークンで認証し、Jiraに接続
        jira_client = JIRA(server=server, basic_auth=(email, token))
        print("✅ 認証に成功しました。")
    except Exception as e:
        print(f"❌ 認証に失敗しました: {e}")
        return None

    print(f"\n以下のJQLを実行します:\n  {jql}\n")
    try:
        # JQLを実行して課題を検索
        # maxResults=False を指定すると、件数上限なしで全件取得します
        searched_issues = jira_client.search_issues(jql, maxResults=False)
        print("✅ 検索が完了しました。")
        return searched_issues
    except Exception as e:
        print(f"❌ JQLの実行に失敗しました: {e}")
        return None

# --- メインの実行部分 ---
if __name__ == "__main__":
    
    # 関数を呼び出してJQLを実行
    issues = search_jira_issues(JIRA_SERVER, JIRA_EMAIL, JIRA_API_TOKEN, JQL_QUERY)

    # 結果があれば表示する
    if issues:
        print(f"\n--- 検索結果 ({len(issues)}件) ---")
        if not issues:
            print("該当する課題はありませんでした。")
        else:
            # 取得した課題を一つずつ表示
            for issue in issues:
                # 担当者がいれば名前を、いなければ「未割り当て」と表示
                assignee = issue.fields.assignee.displayName if issue.fields.assignee else "未割り当て"
                
                print(
                    f"キー: {issue.key:<10} | "
                    f"ステータス: {issue.fields.status.name:<10} | "
                    f"担当者: {assignee:<15} | "
                    f"件名: {issue.fields.summary}"
                )
        print("\n--- 処理終了 ---")