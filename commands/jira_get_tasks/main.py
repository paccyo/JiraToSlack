

class Command_Jira_Get_Tasks_Responce:    
    
    def __init__(self):
          pass
    
    def execute(self, body):
          text = body["text"]
          responce = f"受け取ったドキュメント： {text}"
          return responce
