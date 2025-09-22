# main.py

import os
import sys
from slack_bolt import App
from slack_bolt.adapter.google_cloud_functions import SlackRequestHandler
from dotenv import load_dotenv
import commands

load_dotenv()

# --- Start: Added Code for Debugging ---
# 環境変数を取得
slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
slack_signing_secret = os.environ.get("SLACK_SIGNING_SECRET")

# 環境変数が設定されているか確認
if not slack_bot_token:
    print("FATAL ERROR: Environment variable SLACK_BOT_TOKEN is not set.", file=sys.stderr)
    sys.exit(1)
if not slack_signing_secret:
    print("FATAL ERROR: Environment variable SLACK_SIGNING_SECRET is not set.", file=sys.stderr)
    sys.exit(1)
# --- End: Added Code for Debugging ---

# Botを初期化
app = App(
    token=slack_bot_token,
    signing_secret=slack_signing_secret,
    process_before_response=True # 3秒タイムアウトを回避するために推奨
)

# Register commands
commands.register_commands(app)

# Cloud Functionsのエントリーポイント
handler = SlackRequestHandler(app)
def handle_slack_events(req):
    """Slackからのリクエストを処理する関数"""
    return handler.handle(req)

# if __name__ == "__main__":
#     app.start(port=int(os.environ.get("PORT", 3000)))