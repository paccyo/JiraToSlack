# commands/add_user/main.py
# commands/add_user/main.py
from google.cloud import firestore

class CommandAddUserResponce:
    def __init__(self):
        self.db = firestore.Client()

    def execute(self, user_id, user_name, email):
        """
        ユーザー情報をFirestoreに保存する（重複チェックあり）
        """
        try:
            # emailで既存ユーザーがいないかチェック
            users_ref = self.db.collection('slack_users')
            query = users_ref.where('email', '==', email).limit(1).stream()

            if len(list(query)) > 0:
                return f"メールアドレス {email} はすでに登録されています。"

            # ユーザー情報を保存
            doc_ref = users_ref.document(user_id)
            doc_ref.set({
                'user_name': user_name,
                'email': email
            })
            return f"ユーザー {user_name} ({email}) を登録しました。"
        except Exception as e:
            return f"エラーが発生しました: {e}"
