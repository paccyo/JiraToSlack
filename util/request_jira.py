import os
from jira import JIRA, JIRAError
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

class RequestJiraRepository:
    def __init__(self):
        # 環境変数の読み込み
        JIRA_SERVER = os.getenv("JIRA_DOMAIN")
        JIRA_EMAIL = os.getenv("JIRA_EMAIL")
        JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
        self.project_key = os.getenv("JIRA_PROJECT_KEY")
        try:
            self.sp_env = os.getenv("JIRA_STORY_POINTS_FIELD")
        except Exception as e:
            print(f"error: {e}")
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


    def request_jql(self, query, max_results=False, fileds=None):
        print(f"request jql query: \n{query}")
        try:
            # JQLを実行して課題を検索
            searched_issues = self.jira_client.search_issues(query, maxResults=max_results, fields=fileds)
            print("✅ 検索が完了しました。")
            return searched_issues
        except Exception as e:
            print(f"❌ JQLの実行に失敗しました: {e}")
            return None
    
    def get_issue(self, issue_key, fields=None, expand=None):
        return self.jira_client.issue(issue_key)
    
    def build_jql_from_json(self, data: dict) -> str:

        
        if self.project_key:
            conditions = [f'project = "{self.project_key}"']
        else:
            conditions = []

        # JQL内で引用符で囲む必要のない特別なキーワードや関数を定義
        jql_keywords = {
            "currentUser()", "isEmpty()", "now()", "endOfDay()", "endOfWeek()",
            "startOfMonth()", "Highest", "High", "Medium", "Low", "Lowest", "EMPTY"
        }

        process_order = [
            "project", "reporter", "assignee", "issuetype", "status",
            "priority", "text", "duedate", "created", "resolved"
        ]

        for field in process_order:
            value = data.get(field)

            # 値がnullの場合はスキップ
            if value is None:
                continue
            
            # 文字列の場合 (例: project = "MYPROJ")
            if isinstance(value, str):
                if field == 'text':
                    conditions.append(f'text ~ "{value}"')
                else:
                    is_function = '(' in value and ')' in value
                    formatted_value = value if value in jql_keywords or is_function else f'"{value}"'
                    conditions.append(f'{field} = {formatted_value}')

            # 辞書の場合 (単一の条件)
            elif isinstance(value, dict):
                operator = value.get("operator", "=").upper()
                op_value = value.get("value")

                if op_value is None:
                    continue
                
                if operator in ["IN", "NOT IN"] and isinstance(op_value, list):
                    quoted_items = [f'"{item}"' for item in op_value]
                    formatted_value = f'({", ".join(quoted_items)})'
                    conditions.append(f'{field} {operator} {formatted_value}')
                elif isinstance(op_value, str):
                    is_function = '(' in op_value and ')' in op_value
                    formatted_value = op_value if op_value in jql_keywords or is_function else f'"{op_value}"'
                    conditions.append(f'{field} {operator} {formatted_value}')

            # リストの場合 (複数の条件)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        operator = item.get("operator", "=").upper()
                        op_value = item.get("value")
                        if op_value is None:
                            continue
                        if isinstance(op_value, str):
                            is_function = '(' in op_value and ')' in op_value
                            formatted_value = op_value if op_value in jql_keywords or is_function else f'"{op_value}"'
                            conditions.append(f'{field} {operator} {formatted_value}')

        # 全ての条件を " AND " で連結して返す
        jql_string = " AND ".join(conditions)

        # orderBy があれば、JQLに追加
        if data.get("orderBy"):
            jql_string += f' ORDER BY {data.get("orderBy")}'

        return jql_string
    

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

        # 完了日を取得・フォーマット
        if issue.fields.resolutiondate:
            resolution_date_obj = datetime.strptime(issue.fields.resolutiondate, '%Y-%m-%dT%H:%M:%S.%f%z')
            resolution_date = resolution_date_obj.strftime('%Y-%m-%d %H:%M')
        else:
            resolution_date = "未完了"

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
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*完了日*: {resolution_date}"
                    }
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "ToDo",
                            "emoji": True
                        },
                        "value": issue.key,
                        "action_id": "move_Todo"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "In_progress",
                            "emoji": True
                        },
                        "value": issue.key,
                        "action_id": "move_in_progress"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "REVIEWING",
                            "emoji": True
                        },
                        "value": issue.key,
                        "action_id": "move_reviewing"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Abort",
                            "emoji": True
                        },
                        "value": issue.key,
                        "action_id": "move_abort"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "完了",
                            "emoji": True
                        },
                        "value": issue.key,
                        "action_id": "move_compleated"
                    }
                ]
            }
        ]
        return blocks

    def issue_change_status(self, user_email, issue_key, status):
        """Jira課題を指定されたステータスに移動させる関数"""
        print(f"DEBUG: issue_change_status called. issue='{issue_key}', status='{status}', user='{user_email}'")
        
        try:
            transitions = self.jira_client.transitions(issue_key)
            
            transition_id = None
            for t in transitions:
                # 渡されたstatus引数と移動先のステータス名を比較
                # .lower()で両方を小文字にし、大文字/小文字の違いを吸収
                if t['to']['name'].lower() == status.lower():
                    transition_id = t['id']
                    break 
            
            if transition_id:
                self.jira_client.transition_issue(issue_key, transition_id)
                print(f"✅ Successfully transitioned issue {issue_key} to '{status}'")
            else:
                # 目的のステータスへのトランジションが見つからなかった場合のログ
                available_transitions = [t['to']['name'] for t in transitions]
                print(f"⚠️ Could not find a transition to '{status}' for issue {issue_key}.")
                print(f"   Available transitions are: {available_transitions}")

        except JIRAError as e:
            print(f"❌ Jira API Error for issue {issue_key}: Status {e.status_code} - {e.text}")
        except Exception as e:
            print(f"❌ An unexpected error occurred: {e}")


    def get_scrum_board(self, board_id = 1):
        print("\n🔎 Scrumボードを検索中...")
        all_boards = self.jira_client.boards()
        print(all_boards)
        scrum_board = None
        for board in all_boards:
            # print(board.raw.get("id"))
            if board.raw.get("id") == board_id:
                scrum_board = board
                return scrum_board.raw
        
        if not scrum_board:
            print("❌ Scrumタイプのボードが見つかりませんでした。")
            return None
        

    def get_board_active_sprint(self, board_id):
        print("\n🔎 アクティブなスプリントを検索中...")
        active_sprints = self.jira_client.sprints(board_id=board_id, state='active')
        if active_sprints:
            return active_sprints[0].raw
        else:
            print("❌ アクティブなスプリントはありませんでした。")
            return None

    def get_story_point_field(self):
        print("\n🔎 ストーリーポイントフィールドを検索中...")
        all_fields = self.jira_client.fields()
        for field in all_fields:
            if field.get("schema", {}).get("custom") == "com.pyxis.greenhopper.jira:jsw-story-points":
                story_points_field_id = field["id"]
                break

