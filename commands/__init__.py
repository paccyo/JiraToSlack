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
    def handle_jira_get_tasks_command(ack, body, say):
        ack()
        user_query = body["text"]
        say(f"user query: {user_query}")
        say("処理中...")
        command_jira_get_tasks_repository = CommandJiraGetTasksRepository()
        responce = command_jira_get_tasks_repository.execute(body)
        say(responce)