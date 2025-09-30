# from prompts import get_system_prompt_generate_jql, JQLQuerySchema
# from request_jql import RequestJqlRepository

from commands.jira_get_tasks.prompts import get_system_prompt_generate_jql, JQLQuerySchema
from util.request_jql import RequestJqlRepository

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
                request_jql_repository = RequestJqlRepository()
                jql_query = request_jql_repository.build_jql_from_json(gemini_result)
<<<<<<< HEAD
                jira_results = request_jql_repository.execute(jql_query)
=======
                limit = gemini_result.get("limit")
                jira_results = request_jql_repository.execute(jql_query, max_results=limit)
>>>>>>> develop
                
                responce = {}

                for jira_result in jira_results:
<<<<<<< HEAD
                    block = self.format_jira_issue_for_slack(jira_result)
=======
                    block = request_jql_repository.format_jira_issue_for_slack(jira_result)
>>>>>>> develop
                    responce[jira_result.key] = block

                return responce
            
            except Exception as e:
                return f"Request JQL error:{e}"
            
        except Exception as e:
            return f"An error occurred: {e}"
        


<<<<<<< HEAD
    def format_jira_issue_for_slack(self, issue):
        # 課題のURLを取得
        issue_url = issue.permalink()

        # 担当者がいるかどうかを確認
        if issue.fields.assignee:
            assignee_name = issue.fields.assignee.displayName
        else:
            assignee_name = "未割り当て"

        # ステータス名を取得
        status_name = issue.fields.status.name

        # Block KitのJSON構造を構築
        blocks = [
            {
                "type": "divider" # 区切り線
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    # 課題の要約を太字にし、課題キーにURLをリンクさせる
                    "text": f" *<{issue_url}|{issue.key}>: {issue.fields.summary}*"
                }
            },
            {
                "type": "context", # 補足情報セクション
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*ステータス*: {status_name}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*担当者*: {assignee_name}"
                    }
                ]
            }
        ]
        return blocks
=======

>>>>>>> develop

        

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    query = "今日の13:00から14:00の間に完了したタスク"
    repository = CommandJiraGetTasksRepository()
    print(f"resuest query:{query}")
    print(repository.execute(body={"text":query}))
