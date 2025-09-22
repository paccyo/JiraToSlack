from commands.jira_get_tasks.prompts import get_system_prompt_generate_jql,get_user_prompt_generate_jql
import os

from google import genai
from google.genai import types


class Command_Jira_Get_Tasks_Responce:    
    
    def __init__(self):
        # 環境変数を取得
        gemini_api_key = os.environ.get("GEMINI_API_KEY")

        if not gemini_api_key:
            raise ValueError("FATAL ERROR: Environment variable GEMINI_API_KEY is not set.")
        
        self.client = genai.Client(
            api_key=gemini_api_key,
        )
    
    def execute(self, body):
        system_prompt = get_system_prompt_generate_jql()
        text = body["text"]
        try:
            responce = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt
                )
            )

            return responce.text
        except Exception as e:
            return f"An error occurred: {e}"