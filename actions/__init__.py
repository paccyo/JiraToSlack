import asyncio

from util.get_jira_data import GetJiraData
from util.request_jira import RequestJiraRepository
from util.get_slack_email import GetSlackUserIdToEmail



def change_status(say, user_id, issue_key, status):
    """Jira課題を完了ステータスに移動させる関数（バックグラウンドで実行）"""
    get_skack_user_id_to_email = GetSlackUserIdToEmail()
    slack_email_to_register = get_skack_user_id_to_email.get_user_email(user_id)
    
    get_jira_data = GetJiraData()
    email = get_jira_data.get_slack_email_to_jira_email(slack_email_to_register)

    request_jira_repository = RequestJiraRepository()
    request_jira_repository.issue_change_status(email, issue_key, status)
    
    return


def register_actions(app):
    """
    Registers all slash commands with the provided app instance.
    """

    @app.action("move_Todo")
    def handle_move_todo_command(ack, body, say):
        ack()
        try:
            change_status(say, body["user"]["id"], body["actions"][0]["value"], "TODO")
            say(f"✅ Jira課題 `{body['actions'][0]['value']}` のステータスをTODOに変更しました。")
            return
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            say(f"エラーが発生しました: {e}")
            return 
        

    @app.action("move_in_progress")
    def handle_move_in_progress_command(ack, body, say):
        ack()
        try:
            change_status(say, body["user"]["id"], body["actions"][0]["value"], "IN_progress")
            say(f"✅ Jira課題 `{body['actions'][0]['value']}` のステータスをIN_progressに変更しました。")
            return 
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            say(f"エラーが発生しました: {e}")
            return
        
    @app.action("move_reviewing")
    def handle_move_in_progress_command(ack, body, say):
        ack()
        try:
            change_status(say, body["user"]["id"], body["actions"][0]["value"], "REVIEWING")
            say(f"✅ Jira課題 `{body['actions'][0]['value']}` のステータスをREVIEWINGに変更しました。")
            return 
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            say(f"エラーが発生しました: {e}")
            return

    @app.action("move_abort")
    def handle_move_abort_command(ack, body, say):
        ack()
        try:
            change_status(say, body["user"]["id"], body["actions"][0]["value"], "Abort")
            say(f"✅ Jira課題 `{body['actions'][0]['value']}` のステータスをAbortに変更しました。")
            return
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            say(f"エラーが発生しました: {e}")
            return


    @app.action("move_compleated")
    def handle_move_compleated_command(ack, body, say):
        ack()
        try:
            change_status(say, body["user"]["id"], body["actions"][0]["value"], "完了")
            say(f"✅ Jira課題 `{body['actions'][0]['value']}` を完了にしました。")
            return
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            say(f"エラーが発生しました: {e}")
            return