# util/get_jira_email.py
from google.cloud import firestore

class GetJiraData:
    def __init__(self):
        """
        Firestoreクライアントを初期化する
        """
        self.db = firestore.Client()

    def get_slack_email_to_jira_email(self, slack_email):
        """
        Slackのemailを基にFirestoreを検索し、Jiraのemailを返す
        """
        if not slack_email:
            return None

        try:
            users_ref = self.db.collection('slack_users')
            query = users_ref.where('slack_email', '==', slack_email).limit(1).stream()

            user_list = list(query)
            if not user_list:
                return None # ユーザーが見つからない

            user_data = user_list[0].to_dict()
            return user_data.get('jira_email')

        except Exception as e:
            print(f"FirestoreからのJira email取得中にエラーが発生しました: {e}")
            return None
