
def register_actions(app):
    """
    Registers all slash commands with the provided app instance.
    """
    @app.action("/add_user")
    def handle_add_user_command(ack, body, say, client):
        ack()
