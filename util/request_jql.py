import os
from jira import JIRA

class RequestJqlRepository:
    def __init__(self):
        # 環境変数の読み込み
        JIRA_SERVER = os.getenv("JIRA_DOMAIN")
        JIRA_EMAIL = os.getenv("JIRA_EMAIL")
        JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
        try:
            # メールアドレスとAPIトークンで認証し、Jiraに接続
            self.jira_client = JIRA(
                server=JIRA_SERVER, 
                basic_auth=(
                    JIRA_EMAIL, 
                    JIRA_API_TOKEN
                )
            )
            print("✅ 認証に成功しました。")
        except Exception as e:
            print(f"❌ 認証に失敗しました: {e}")
            return None


    def execute(self, query):
        print(f"request jql query: \n{query}")
        try:
            # JQLを実行して課題を検索
            # maxResults=False を指定すると、件数上限なしで全件取得します
            searched_issues = self.jira_client.search_issues(query, maxResults=False)
            print("✅ 検索が完了しました。")
            return searched_issues
        except Exception as e:
            print(f"❌ JQLの実行に失敗しました: {e}")
            return None
    
    def build_jql_from_json(self, data: dict) -> str:

        conditions = []

        # JQL内で引用符で囲む必要のない特別なキーワードや関数を定義
        jql_keywords = {
            "currentUser()", "isEmpty()", "now()", "endOfDay()", "endOfWeek()",
            "startOfMonth()", "Highest", "High", "Medium", "Low", "Lowest"
        }

        process_order = [
            "project", "reporter", "assignee", "issuetype", "status",
            "priority", "text", "duedate", "created"
        ]

        for field in process_order:
            value = data.get(field)

            # 値がnullの場合はスキップ
            if value is None:
                continue
            
            if isinstance(value, str):
                # 'text'フィールドは'~'演算子を使用
                if field == 'text':
                    conditions.append(f'text ~ "{value}"')

                # その他のフィールドは'='演算子を使用
                else:
                    # 値が特別なキーワードでなければ引用符で囲む
                    formatted_value = value if value in jql_keywords else f'"{value}"'
                    conditions.append(f'{field} = {formatted_value}')

            # 値が比較演算子を持つオブジェクトの場合の処理
            elif isinstance(value, dict):
                operator = value.get("operator", "=").upper()
                op_value = value.get("value")

                if op_value is None:
                    continue
                
                # IN や NOT IN 演算子で、値がリストの場合
                if operator in ["IN", "NOT IN"] and isinstance(op_value, list):
                    # リストの各要素を引用符で囲み、カンマで連結
                    quoted_items = [f'"{item}"' for item in op_value]
                    formatted_value = f'({", ".join(quoted_items)})'
                    conditions.append(f'{field} {operator} {formatted_value}')
                
                # その他の演算子で、値が文字列の場合
                elif isinstance(op_value, str):
                    formatted_value = op_value if op_value in jql_keywords else f'"{op_value}"'
                    conditions.append(f'{field} {operator} {formatted_value}')

        # 全ての条件を " AND " で連結して返す
        return " AND ".join(conditions)
    

    def format_jira_issue_for_slack(self, issue):
        # 課題のURLを取得
        issue_url = issue.permalink()

        # 担当者がいるかどうかを確認
        if issue.fields.assignee:
            assignee_name = issue.fields.assignee.displayName
        else:
            assignee_name = "未割り当て"

        # ステータス名を取得
        status_name = issue.fields.status.name

        # 優先度名を取得
        priority_name = issue.fields.priority.name if issue.fields.priority else "なし"

        # 期日を取得
        due_date = issue.fields.duedate if issue.fields.duedate else "なし"

        # Block KitのJSON構造を構築
        blocks = [
            {
                "type": "divider" # 区切り線
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    # 課題の要約を太字にし、課題キーにURLをリンクさせる
                    "text": f" *<{issue_url}|{issue.key}>: {issue.fields.summary}*"
                }
            },
            {
                "type": "context", # 補足情報セクション
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*ステータス*: {status_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*担当者*: {assignee_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*優先度*: {priority_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*期日*: {due_date}"
                    }
                ]
            }
        ]
        return blocks