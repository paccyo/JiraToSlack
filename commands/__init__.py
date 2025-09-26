from commands.jira.main import Command_Jira_Responce
from commands.jira_get_tasks.main import Command_Jira_Get_Tasks_Responce


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
        ack()
        user_query = body["text"]
        say(f"user query: {user_query}")
        say("処理中...")
        image_path = run_jira_backlog_dashboard()
        if image_path:
            # Slack APIで画像ファイルをアップロード
            app.client.files_upload(
                channels=body["channel_id"],
                file=image_path,
                title="Jiraバックログダッシュボード"
            )
            say("画像を送信しました")
        else:
            say("画像生成に失敗しました")