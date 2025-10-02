# sheduler/main.py
import sys
from datetime import datetime, date

from util.request_jql import RequestJqlRepository

class SchedulerTaskHandler:
    def execute(self, app, db, message_data_str):
        """
        Firestoreから全ユーザーを取得し、Slack DMを送信する
        """
        print("特別なタスクを実行し、ユーザーのDMに通知します。")
        
        try:
            # JQLリクエストリポジトリのインスタンス化
            request_jql_repository = RequestJqlRepository()
        except Exception as e:
            return f"Initilized JQLRepository error:{e}"


        try:
            # Firestoreから全ユーザーを取得
            users_ref = db.collection('slack_users').stream()
            
            sent_count = 0
            for user_doc in users_ref:
                user_data = user_doc.to_dict()
                user_email = user_data.get("email")

                if not user_email:
                    print(f"ドキュメント {user_doc.id} にemailフィールドがありません。スキップします。")
                    continue

                try:
                    # メールアドレスからユーザー情報を検索
                    user_info_response = app.client.users_lookupByEmail(email=user_email)
                    user_id = user_info_response["user"]["id"]
                    
                    # JQLクエリを構築
                    jql_query = f'assignee = "{user_email}" AND status in ("To Do", "IN_progress")'
                    
                    # JQLを実行してJiraからタスクを取得
                    jira_results = request_jql_repository.execute(jql_query)
                    print(f"Jiraから {len(jira_results) if jira_results else 0} 件のタスクを取得しました。") # デバッグ用ログ

                    blocks = []
                    found_any_tasks = False

                    if jira_results:
                        today = date.today().isoformat()

                        # カテゴリ1: 今日が期限のタスク
                        tasks_due_today = [issue for issue in jira_results if issue.fields.duedate and issue.fields.duedate == today]
                        blocks.append({"type": "header", "text": {"type": "plain_text", "text": "今日が期限のタスク"}})
                        if tasks_due_today:
                            found_any_tasks = True
                            for issue in tasks_due_today:
                                blocks.extend(request_jql_repository.format_jira_issue_for_slack(issue))
                        else:
                            blocks.append({
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "今日が期限のタスクはありません。"
                                }
                            })

                        # 残りのタスク（今日が期限のものを除く）
                        remaining_tasks = [issue for issue in jira_results if not (issue.fields.duedate and issue.fields.duedate == today)]

                        # カテゴリ2: 優先度の高いタスク
                        def priority_sort_key(issue):
                            if issue.fields.priority:
                                return int(issue.fields.priority.id)
                            return sys.maxsize # 優先度がないものは最後に
                        
                        sorted_by_priority = sorted(remaining_tasks, key=priority_sort_key)
                        high_priority_tasks = [t for t in sorted_by_priority if t.fields.priority][:3]

                        if high_priority_tasks:
                            found_any_tasks = True
                            blocks.append({"type": "header", "text": {"type": "plain_text", "text": "優先度の高いタスク"}})
                            for issue in high_priority_tasks:
                                blocks.extend(request_jql_repository.format_jira_issue_for_slack(issue))

                        # カテゴリ3: 期日が近いタスク
                        tasks_with_duedate = [issue for issue in remaining_tasks if issue.fields.duedate]
                        def duedate_sort_key(issue):
                            return datetime.strptime(issue.fields.duedate, "%Y-%m-%d").date()
                        
                        upcoming_tasks = sorted(tasks_with_duedate, key=duedate_sort_key)[:3]
                        if upcoming_tasks:
                            found_any_tasks = True
                            blocks.append({"type": "header", "text": {"type": "plain_text", "text": "期日が近いタスク"}})
                            for issue in upcoming_tasks:
                                blocks.extend(request_jql_repository.format_jira_issue_for_slack(issue))

                    if not found_any_tasks:
                        # jiraからタスクが取れなかった場合は、総合的な「タスクなし」メッセージに差し替える
                        if not jira_results:
                            blocks = [{
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "現在、ToDoまたは進行中のタスクはありません。"
                                }
                            }]

                    # 取得したユーザーIDを 'channel' に指定してDMを送信
                    app.client.chat_postMessage(
                        channel=user_id,
                        text="今日のタスク一覧です。",
                        blocks=blocks
                    )
                    print(f"Slackユーザー ({user_email}) のDMにメッセージを送信しました。")
                    sent_count += 1

                except Exception as slack_e:
                    print(f"Slackユーザー ({user_email}) へのDM送信でエラーが発生しました: {slack_e}", file=sys.stderr)
                    # 一人のエラーで全体を止めない
                    continue
            
            return f"タスク完了。{sent_count}人のユーザーに通知しました。"

        except Exception as e:
            print(f"スケジューラタスクの実行中にエラーが発生しました: {e}", file=sys.stderr)
            return "タスク実行中にエラーが発生しました。"

