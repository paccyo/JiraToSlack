# commands/add_user/main.py
# commands/add_user/main.py
from google.cloud import firestore

class CommandAddUserResponce:
    def __init__(self):
        self.db = firestore.Client()

    def execute(self, user_id, user_name, slack_email, jira_email):
        """
        ユーザー情報をFirestoreに保存する（重複チェックあり）
        """
        try:
            # emailで既存ユーザーがいないかチェック
            users_ref = self.db.collection('slack_users')

            query = users_ref.where('slack_email', '==', slack_email).limit(1).stream()
            if len(list(query)) > 0:
                return f"メールアドレス {slack_email} はすでに登録されています。"

            query = users_ref.where('jira_email', '==', jira_email).limit(1).stream()
            if len(list(query)) > 0:
                return f"メールアドレス {jira_email} はすでに登録されています。"

            # ユーザー情報を保存
            doc_ref = users_ref.document(user_id)
            doc_ref.set({
                'user_name': user_name,
                'slack_email': slack_email,
                'jira_email': jira_email,
                'created_at': firestore.SERVER_TIMESTAMP
            })
            return f"Slackユーザー {user_name} ({slack_email}) を登録しました。\nJiraユーザー: {jira_email}"
        except Exception as e:
            return f"エラーが発生しました: {e}"
