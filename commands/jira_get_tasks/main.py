import os
import google.generativeai as genai

class Command_Jira_Get_Tasks_Responce:    
    
    def __init__(self):
        gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("FATAL ERROR: Environment variable GEMINI_API_KEY is not set.")

        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('Gemini 2.5 Flash-Lite')
    
    def execute(self, body):
        text = body["text"]
        try:
            response = self.model.generate_content(text)
            return response.text
        except Exception as e:
            return f"An error occurred: {e}"