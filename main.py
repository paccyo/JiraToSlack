# main.py

import os
import sys
import base64
import json
from slack_bolt import App
from slack_bolt.adapter.google_cloud_functions import SlackRequestHandler
from dotenv import load_dotenv
from google.cloud import firestore
import commands
from sheduler.main import SchedulerTaskHandler

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

# --- Slack App と Firestore の初期化 ---
app = App(
    token=slack_bot_token,
    signing_secret=slack_signing_secret,
    process_before_response=True
)
db = firestore.Client()
commands.register_commands(app)
slack_handler = SlackRequestHandler(app)


# --- Pub/Sub メッセージを処理する関数 ---
def handle_pubsub_message(data: dict):
    """Pub/Subメッセージをデコードし、タスクハンドラに処理を委譲する"""
    try:
        message_data_str = base64.b64decode(data["message"]["data"]).decode("utf-8")
        message_data = json.loads(message_data_str)
        print(f"Pub/Subからメッセージを受信しました: {message_data}")

        if message_data.get("flag") == "execute_special_task":
            # ロジックをSchedulerTaskHandlerに委譲
            task_handler = SchedulerTaskHandler()
            result = task_handler.execute(app, db, message_data_str)
            print(result)
        
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


# Cloud Functions entry point shim (for gcloud --entry-point=handle_slack_events)
def handle_slack_events(req):
    return main_handler(req)
