import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


from dotenv import load_dotenv

load_dotenv()


class GetSlackData:
    def __init__(self):
        try:
            SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
            self.client = WebClient(token=SLACK_BOT_TOKEN)
        except Exception as e:
            print(f"Error: {e}")
        

    def get_user_email(self, user_id):
        user_info = self.client.users_info(user=user_id)
        slack_email = user_info["user"]["profile"]["email"]
        return slack_email
    
    def get_channel_id(self, channel_name: str) -> str | None:
        """
        チャンネル名からチャンネルIDを取得する
        """
        try:
            for result in self.client.conversations_list(limit=100):
                for channel in result["channels"]:
                    if channel["name"] == channel_name:
                        return channel["id"] # チャンネルIDを返す
        except SlackApiError as e:
            print(f"Error fetching conversations: {e}")
        
        return None # チャンネルが見つからなかった場合