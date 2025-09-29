# commands/del_user/main.py
from google.cloud import firestore

class Command_Del_User_Responce:
    def __init__(self):
        self.db = firestore.Client()

    def execute(self, user_id):
        """
        ユーザー情報をFirestoreから削除する
        """
        try:
            doc_ref = self.db.collection('slack_users').document(user_id)
            doc_ref.delete()
            return f"ユーザーID {user_id} の情報を削除しました。"
        except Exception as e:
            return f"エラーが発生しました: {e}"
