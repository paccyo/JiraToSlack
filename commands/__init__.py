
import os
from commands.jira.main import Command_Jira_Responce
from commands.jira_get_tasks.main import Command_Jira_Get_Tasks_Responce

# Jiraバックログダッシュボード画像生成関数
def run_jira_backlog_dashboard():
    from .jira_backlog_report.main import run_dashboard_and_get_image
    return run_dashboard_and_get_image()


def register_commands(app):
    """
    Registers all slash commands with the provided app instance.
    """
    @app.command("/jira")
    def handle_jira_command(ack, say):
        ack()
        command_jira_repository = Command_Jira_Responce()
        responce = command_jira_repository.execute()
        say(responce)

    @app.command("/jira_get_tasks")
    def handle_jira_get_tasks_command(ack, body, say):
        ack()
        user_query = body["text"]
        say(f"user query: {user_query}")
        say("処理中...")
        command_jira_get_tasks_repository = Command_Jira_Get_Tasks_Responce()
        responce = command_jira_get_tasks_repository.execute(body)
        say(responce)

    from . import run_jira_backlog_dashboard

    @app.command("/jira_backlog_report")
    def handle_jira_backlog_report_command(ack, body, say):
        print("LOG: /jira_backlog_report command received")
        try:
            ack()
            print("LOG: ack() completed")
            print(f"LOG: body = {body}")
            user_query = body.get("text", "")
            print(f"LOG: user_query = {user_query}")
            say(f"user query: {user_query}")
            print("LOG: sent user query message")
            say("処理中...")
            print("LOG: sent '処理中...' message")
            print("LOG: calling run_jira_backlog_dashboard()")
            image_path = run_jira_backlog_dashboard()
            print(f"LOG: run_jira_backlog_dashboard() returned: {image_path}")
            if not image_path or not os.path.exists(image_path):
                print(f"LOG: image_path invalid or file does not exist: {image_path}")
                say("画像生成に失敗しました")
                print("LOG: sent '画像生成に失敗しました' message")
                return
            channel_id = body.get("channel_id")
            if not channel_id:
                print(f"LOG: channel_id not found in body: {body}")
                say("Slackリクエストにchannel_idが含まれていません")
                return
            try:
                print(f"LOG: uploading image from path: {image_path} to channel: {channel_id}")
                app.client.files_upload(
                    channels=channel_id,
                    file=image_path,
                    title="Jiraバックログダッシュボード"
                )
                print("LOG: image upload completed")
                say("画像を送信しました")
                print("LOG: sent '画像を送信しました' message")
            except Exception as e:
                print(f"LOG: files_upload error: {e}")
                say(f"画像送信時にエラー: {e}")
        except Exception as e:
            print(f"LOG: ハンドラ全体で例外: {e}")
            say(f"コマンド実行時にエラー: {e}")