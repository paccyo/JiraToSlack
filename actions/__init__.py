from util.get_jira_data import GetJiraData
from util.request_jira import RequestJiraRepository



def register_actions(app):
    """
    Registers all slash commands with the provided app instance.
    """

    @app.action("move_Todo")
    def handle_move_todo_command(ack, body, say):
        ack()

        try:
            try:
                get_jira_data = GetJiraData()
                email = get_jira_data.get_slack_email_to_jira_email(body["user"]["email"])
            except Exception as e:
                say(f"エラーが発生しました: {e}")
                return
            
            issue_key = body["actions"][0]["value"]
            request_jira_repository = RequestJiraRepository()
            request_jira_repository.issue_change_status(email, issue_key, "To Do")
            say(f"✅ Jira課題 `{issue_key}` のステータスをToDoに変更しました。")
        except Exception as e:
            say(f"エラーが発生しました: {e}")
            return
        

    @app.action("move_in_progress")
    def handle_move_todo_command(ack, body, say):
        ack()

        try:
            try:
                get_jira_data = GetJiraData()
                email = get_jira_data.get_slack_email_to_jira_email(body["user"]["email"])
            except Exception as e:
                say(f"エラーが発生しました: {e}")
                return            
            issue_key = body["actions"][0]["value"]
            request_jira_repository = RequestJiraRepository()
            request_jira_repository.issue_change_status(email, issue_key, "IN_progress")
            say(f"✅ Jira課題 `{issue_key}` のステータスをIN_progressに変更しました。")
        except Exception as e:
            say(f"エラーが発生しました: {e}")
            return

    @app.action("move_abort")
    def handle_move_todo_command(ack, body, say):
        ack()

        try:
            try:
                get_jira_data = GetJiraData()
                email = get_jira_data.get_slack_email_to_jira_email(body["user"]["email"])
            except Exception as e:
                say(f"エラーが発生しました: {e}")
                return            
            issue_key = body["actions"][0]["value"]
            
            request_jira_repository = RequestJiraRepository()
            request_jira_repository.issue_change_status(email, issue_key, "Abort")
            say(f"✅ Jira課題 `{issue_key}` のステータスをAbortに変更しました。")
        except Exception as e:
            say(f"エラーが発生しました: {e}")
            return

    @app.action("move_compleated")
    def handle_move_todo_command(ack, body, say):
        ack()

        try:
            try:
                get_jira_data = GetJiraData()
                email = get_jira_data.get_slack_email_to_jira_email(body["user"]["email"])
            except Exception as e:
                say(f"エラーが発生しました: {e}")
                return
            issue_key = body["actions"][0]["value"]
            request_jira_repository = RequestJiraRepository()
            request_jira_repository.issue_change_status(email, issue_key, "完了")
            say(f"✅ Jira課題 `{issue_key}` のステータスを完了に変更しました。")
        except Exception as e:
            say(f"エラーが発生しました: {e}")
            return
        


