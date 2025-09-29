from commands.jira.main import Command_Jira_Responce
from commands.jira_get_tasks.main import Command_Jira_Get_Tasks_Responce
from commands.add_user.main import Command_Add_User_Responce
from commands.del_user.main import Command_Del_User_Responce


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

    @app.command("/add_user")
    def handle_add_user_command(ack, body, say, client):
        ack()
        user_id = body["user_id"]
        user_name = body["user_name"]
        
        try:
            # ユーザーのメールアドレスを取得
            user_info = client.users_info(user=user_id)
            email = user_info["user"]["profile"]["email"]
            
            # Firestoreに保存
            command_add_user_repository = Command_Add_User_Responce()
            response = command_add_user_repository.execute(user_id, user_name, email)
            say(response)
        except Exception as e:
            say(f"エラーが発生しました: {e}")

    @app.command("/del_user")
    def handle_del_user_command(ack, body, say):
        ack()
        user_id = body["user_id"]
        
        try:
            # Firestoreから削除
            command_del_user_repository = Command_Del_User_Responce()
            response = command_del_user_repository.execute(user_id)
            say(response)
        except Exception as e:
            say(f"エラーが発生しました: {e}")