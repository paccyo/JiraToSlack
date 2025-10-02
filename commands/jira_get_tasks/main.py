# from prompts import get_system_prompt_generate_jql, JQLQuerySchema
# from request_jql import RequestJiraRepository

from commands.jira_get_tasks.prompts import get_system_prompt_generate_jql, JQLQuerySchema
from util.request_jira import RequestJiraRepository

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
            
            gemini_result = json.loads(clean_json_str)
            print(f"gemini result: \n{gemini_result}")
            # return responce_result
            try:
                # JQLリクエスト
                request_jira_repository = RequestJiraRepository()
                jql_query = request_jira_repository.build_jql_from_json(gemini_result)
                limit = gemini_result.get("limit")
                jira_results = request_jira_repository.execute(jql_query, max_results=limit)
                
                responce = {}

                for jira_result in jira_results:
                    block = request_jira_repository.format_jira_issue_for_slack(jira_result)
                    responce[jira_result.key] = block

                return responce
            
            except Exception as e:
                return f"Request JQL error:{e}"
            
        except Exception as e:
            return f"An error occurred: {e}"
        



        

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    query = "今日の13:00から14:00の間に完了したタスク"
    repository = CommandJiraGetTasksRepository()
    print(f"resuest query:{query}")
    print(repository.execute(body={"text":query}))
