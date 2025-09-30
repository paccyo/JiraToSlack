# sheduler/main.py
import sys

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
                    
                    blocks = [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": "今日のあなたのタスクはこちらです！"
                            }
                        }
                    ]
                    
                    if jira_results:
                        for issue in jira_results:
                            blocks.extend(request_jql_repository.format_jira_issue_for_slack(issue))
                    else:
                        blocks.append({
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "現在、ToDoまたは進行中のタスクはありません。"
                            }
                        })

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

