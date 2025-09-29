# commands/add_user/main.py
from google.cloud import firestore

class Command_Add_User_Responce:
    def __init__(self):
        self.db = firestore.Client()

    def execute(self, user_id, user_name, email):
        """
        ユーザー情報をFirestoreに保存する
        """
        try:
            doc_ref = self.db.collection('slack_users').document(user_id)
            doc_ref.set({
                'user_name': user_name,
                'email': email
            })
            return f"ユーザー {user_name} ({email}) を登録しました。"
        except Exception as e:
            return f"エラーが発生しました: {e}"
