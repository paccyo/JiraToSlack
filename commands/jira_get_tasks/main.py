from prompts import get_system_prompt_generate_jql, JQLQuerySchema
# from commands.jira_get_tasks.prompts import get_system_prompt_generate_jql,get_user_prompt_generate_jql
from request_jql import RequestJqlRepository

import os
import json
import re

from google import genai
from google.genai import types




class CommandJiraGetTasksRepository:    
    
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
                    system_instruction=system_prompt,
                    response_schema=JQLQuerySchema
                )
            )
            # return responce.text
            clean_json_str = re.search(r"\{.*\}", responce.text, re.DOTALL).group(0)
            
            responce_result = json.loads(clean_json_str)

            # return responce_result
            try:
                request_jql_repository = RequestJqlRepository()
                jql_query = request_jql_repository.build_jql_from_json(responce_result)
                result = request_jql_repository.execute(jql_query)

                return result
            
            except Exception as e:
                return f"Request JQL error:{e}"
            
        except Exception as e:
            return f"An error occurred: {e}"
        

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    repository = CommandJiraGetTasksRepository()

    print(repository.execute(body={"text":"完了済のすべてのタスク"}))