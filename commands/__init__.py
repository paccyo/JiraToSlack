import os
import sys


from commands.jira.main import CommandJiraRepository
from commands.jira_get_tasks.main import CommandJiraGetTasksRepository
from commands.add_user.main import CommandAddUserResponce
from commands.del_user.main import CommandDelUserResponce
from commands.jira.main import CommandJiraRepository
from commands.jira_get_tasks.main import CommandJiraGetTasksRepository

# Jiraバックログダッシュボード画像生成関数
def run_jira_backlog_dashboard():
    from .jira_backlog_report.main import run_dashboard_and_get_image
    return run_dashboard_and_get_image()


def register_commands(app):
    """
    Registers all slash commands with the provided app instance.
    """
    @app.command("/add_user")
    def handle_add_user_command(ack, body, say, client):
        ack()
        user_id = body["user_id"]
        user_name = body["user_name"]
        text = body.get("text", "").strip()

        # Slackプロフィールのメールアドレスを取得
        user_info = client.users_info(user=user_id)
        # Slackプロフィールからメールアドレスを取得
        slack_email_to_register = user_info["user"]["profile"]["email"]
        
        try:
            jira_email_to_regester = None
            if text:
                # テキストが提供されていれば、それをメールアドレスとして使用
                jira_email_to_regester = text
            else:
                # テキストがなければ、Slackmのメールアドレスを使用
                jira_email_to_regester = slack_email_to_register 
                

            # Firestoreに保存
            command_add_user_repository = CommandAddUserResponce()
            response = command_add_user_repository.execute(user_id, user_name, slack_email_to_register, jira_email_to_regester)
            say(response)
        except Exception as e:
            say(f"エラーが発生しました: {e}")          

    @app.command("/del_user")                                                                                      
    def handle_del_user_command(ack, body, say):                                                                                               
        ack()                                                                                                                                       
        user_id = body["user_id"]                                                                                                      
        try:                                                                                                               
            # Firestoreから削除                                                                                             
            command_del_user_repository = CommandDelUserResponce()                                              
            response = command_del_user_repository.execute(user_id)                                       
            say(response)                                                                                           
        except Exception as e:                                                                                      
            say(f"エラーが発生しました: {e}")
    
    @app.command("/jira")
    def handle_jira_command(ack, say):
        ack()
        command_jira_repository = CommandJiraRepository()
        responce = command_jira_repository.execute()
        say(responce)

    @app.command("/jira_get_tasks")
    def handle_jira_get_tasks_command(ack, body, say, client):
        ack()
        user_query = body["text"]
        # ユーザーに処理開始を通知
        say(f"「{user_query}」を検索します... :hourglass_flowing_sand:")
        # 1. Jiraから課題リストを取得する
        repo = CommandJiraGetTasksRepository()
        issues_list = repo.execute(body)
        if not issues_list:
            say("該当するJira課題は見つかりませんでした。")
            return
        if isinstance(issues_list, str) and "error" in issues_list.lower():
            # エラーメッセージが返ってきた場合
            say(f"エラーが発生しました: {issues_list}")
            return
        
        for key, issue in issues_list.items():
            try:
                # sayではなくclient.chat_postMessageを使ってblocksを送信
                client.chat_postMessage(
                    channel=body["channel_id"],
                    text=f"Jira課題: {key}", # 通知用のプレーンテキスト
                    blocks=issue
                )
            except Exception as e:
                say(f"課題 {issue.key} の整形または送信中にエラーが発生しました: {e}")

        # say(responce)

    from . import run_jira_backlog_dashboard

    @app.command("/jira_backlog_report")
    def handle_jira_backlog_report_command(ack, body, say):
        print("LOG: /jira_backlog_report command received")
        try:
            ack()
            print("LOG: ack() completed")
            print(f"LOG: body = {body}")
            user_query = body.get("text", "")
            print(f"LOG: user_query = {user_query}")
            say(f"user query: {user_query}")
            print("LOG: sent user query message")
            say("処理中...")
            print("LOG: sent '処理中...' message")
            print("LOG: calling run_jira_backlog_dashboard()")
            image_path = run_jira_backlog_dashboard()
            print(f"LOG: run_jira_backlog_dashboard() returned: {image_path}")
            if not image_path or not os.path.exists(image_path):
                print(f"LOG: image_path invalid or file does not exist: {image_path}")
                say("画像生成に失敗しました")
                print("LOG: sent '画像生成に失敗しました' message")
                return
            channel_id = body.get("channel_id")
            if not channel_id:
                print(f"LOG: channel_id not found in body: {body}")
                say("Slackリクエストにchannel_idが含まれていません")
                return
            try:
                print(f"LOG: uploading image from path: {image_path} to channel: {channel_id}")
                app.client.files_upload_v2(
                    channel=channel_id,
                    file=image_path,
                    filename=os.path.basename(image_path),
                    title="Jiraバックログダッシュボード",
                    initial_comment="Jiraバックログダッシュボードをアップロードしました",
                )
                print("LOG: image upload completed")
                say("画像を送信しました")
                print("LOG: sent '画像を送信しました' message")
            except Exception as e:
                print(f"LOG: files_upload error: {e}")
                say(f"画像送信時にエラー: {e}")
        except Exception as e:
            print(f"LOG: ハンドラ全体で例外: {e}")
            say(f"コマンド実行時にエラー: {e}")
