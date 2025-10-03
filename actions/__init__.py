import actions.change_status.change_status as change_status


def register_actions(app):
    """
    Registers all slash commands with the provided app instance.
    """

    @app.action("move_Todo")
    def handle_move_todo_command(ack, body, say, client):
        ack()
        try:
            change_status(say, client, body, "TODO")
            return
        except Exception as e:
            print(f"ステータスの更新中にエラーが発生しました: {e}")
            say(f"ステータスの更新中にエラーが発生しました: {e}")
            return 
        

    @app.action("move_in_progress")
    def handle_move_in_progress_command(ack, body, say, client):
        ack()
        try:
            change_status(say, client, body, "IN_progress")
            return
        except Exception as e:
            print(f"ステータスの更新中にエラーが発生しました: {e}")
            say(f"ステータスの更新中にエラーが発生しました: {e}")
            return 
        
    @app.action("move_reviewing")
    def handle_move_in_progress_command(ack, body, say, client):
        ack()
        try:
            change_status(say, client, body, "REVIEWING")
            return
        except Exception as e:
            print(f"ステータスの更新中にエラーが発生しました: {e}")
            say(f"ステータスの更新中にエラーが発生しました: {e}")
            return 

    @app.action("move_abort")
    def handle_move_abort_command(ack, body, say, client):
        ack()
        try:
            change_status(say, client, body, "Abort")
            return
        except Exception as e:
            print(f"ステータスの更新中にエラーが発生しました: {e}")
            say(f"ステータスの更新中にエラーが発生しました: {e}")
            return 


    @app.action("move_compleated")
    def handle_move_compleated_command(ack, body, say, client):
        ack()
        try:
            change_status(say, client, body, "完了")
            return
        except Exception as e:
            print(f"ステータスの更新中にエラーが発生しました: {e}")
            say(f"ステータスの更新中にエラーが発生しました: {e}")
            return