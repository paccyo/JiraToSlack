# main.py

import os
import sys
import base64
import json
from slack_bolt import App
from slack_bolt.adapter.google_cloud_functions import SlackRequestHandler
from dotenv import load_dotenv
import commands

# --- 環境変数の読み込みとチェック ---
load_dotenv()
slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
slack_signing_secret = os.environ.get("SLACK_SIGNING_SECRET")

if not slack_bot_token:
    print("FATAL ERROR: Environment variable SLACK_BOT_TOKEN is not set.", file=sys.stderr)
    sys.exit(1)
if not slack_signing_secret:
    print("FATAL ERROR: Environment variable SLACK_SIGNING_SECRET is not set.", file=sys.stderr)
    sys.exit(1)

# --- Slack App の初期化 ---
app = App(
    token=slack_bot_token,
    signing_secret=slack_signing_secret,
    process_before_response=True
)
commands.register_commands(app)
slack_handler = SlackRequestHandler(app)


# --- Pub/Sub メッセージを処理する関数 ---
def handle_pubsub_message(data: dict):
    """Pub/Subメッセージのデータを使って処理を実行し、特定のユーザーのDMに通知する"""
    try:
        # ( ... Base64デコードなどの処理は変更なし ... )
        message_data_str = base64.b64decode(data["message"]["data"]).decode("utf-8")
        message_data = json.loads(message_data_str)
        print(f"Pub/Subからメッセージを受信しました: {message_data}")

        if message_data.get("flag") == "execute_special_task":
            print("フラグを認識しました。特別なタスクを実行し、ユーザーのDMに通知します。")
            
            # ▼▼▼ SlackのDMにメッセージを送信する処理 ▼▼▼
            try:
                # 送信先のメールアドレスを環境変数から取得
                user_email = os.environ.get("SLACK_TARGET_USER_EMAIL")
                if not user_email:
                    print("環境変数 SLACK_TARGET_USER_EMAIL が設定されていません。", file=sys.stderr)
                    return "Configuration error", 500

                # メールアドレスからユーザー情報を検索
                user_info_response = app.client.users_lookupByEmail(email=user_email)
                user_id = user_info_response["user"]["id"]
                
                # Slackに送信するメッセージを作成
                slack_text = f"🤖 Schedulerからタスクが実行されました。\n受信メッセージ: ```{message_data_str}```"

                # 取得したユーザーIDを 'channel' に指定してDMを送信
                app.client.chat_postMessage(
                    channel=user_id,
                    text=slack_text
                )
                print(f"Slackユーザー ({user_email}) のDMにメッセージを送信しました。")

            except Exception as slack_e:
                print(f"SlackへのDM送信でエラーが発生しました: {slack_e}", file=sys.stderr)
            # ▲▲▲ ここまで ▲▲▲
            
        else:
            print("フラグが設定されていないか、値が異なります。")

        return "OK", 200
    except Exception as e:
        print(f"Pub/Subメッセージの処理中にエラーが発生しました: {e}", file=sys.stderr)
        return "Error processing message", 500


# --- Cloud Functions / Cloud Run のメインエントリポイント ---
def main_handler(req):
    """
    リクエストを検査し、Pub/SubかSlackかに応じて処理を振り分ける
    """
    body = req.get_json(silent=True)

    if body and "message" in body and "data" in body["message"]:
        return handle_pubsub_message(body)
    
    return slack_handler.handle(req)