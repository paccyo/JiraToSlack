from commands.jira.main import CommandJiraRepository
from commands.jira_get_tasks.main import CommandJiraGetTasksRepository


def register_commands(app):
    """
    Registers all slash commands with the provided app instance.
    """
    @app.command("/jira")
    def handle_jira_command(ack, say):
        ack()
        command_jira_repository = CommandJiraRepository()
        responce = command_jira_repository.execute()
        say(responce)

    @app.command("/jira_get_tasks")
    def handle_jira_get_tasks_command(ack, body, say, client):
        ack()
        user_query = body["text"]
        # ユーザーに処理開始を通知
        say(f"「{user_query}」を検索します... :hourglass_flowing_sand:")
        # 1. Jiraから課題リストを取得する
        repo = CommandJiraGetTasksRepository()
        issues_list = repo.execute(body)
        if not issues_list:
            say("該当するJira課題は見つかりませんでした。")
            return
        if isinstance(issues_list, str) and "error" in issues_list.lower():
            # エラーメッセージが返ってきた場合
            say(f"エラーが発生しました: {issues_list}")
            return
        
        for key, issue in issues_list.items():
            try:
                # sayではなくclient.chat_postMessageを使ってblocksを送信
                client.chat_postMessage(
                    channel=body["channel_id"],
                    text=f"Jira課題: {key}", # 通知用のプレーンテキスト
                    blocks=issue
                )
            except Exception as e:
                say(f"課題 {issue.key} の整形または送信中にエラーが発生しました: {e}")

        # say(responce)