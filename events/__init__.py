
def register_events(app):

    @app.event("message")
    def handle_message_events(event, say, logger):
        """
        全てのメッセージイベントをリッスンし、DMからのものだけを処理する
        """
        # event['channel_type'] が 'im' の場合、DMと判断
        if event.get("channel_type") == "im":
            
            # Bot自身のメッセージは無視する（無限ループ防止）
            if event.get("bot_id"):
                return

            user_id = event["user"]
            text = event["text"]
            
            try:
                # say()関数は、メッセージが送られてきたチャンネル（この場合はDM）に返信する
                say(
                    text=f"こんにちは <@{user_id}> さん！「{text}」とメッセージを送りましたね。"
                )
                logger.info(f"DMに応答しました (ユーザー: {user_id})")

            except Exception as e:
                logger.error(f"応答中にエラーが発生しました: {e}")


