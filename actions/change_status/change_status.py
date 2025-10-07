from util.get_jira_data import GetJiraData
from util.request_jira import RequestJiraRepository
from util.get_slack_data import GetSlackData


def change_status(say, client, body, status):
    """Jira課題を完了ステータスに移動させる関数（バックグラウンドで実行）"""

    user_id, issue_key = body["user"]["id"], body["actions"][0]["value"]

    get_skack_user_id_to_email = GetSlackData()
    slack_email_to_register = get_skack_user_id_to_email.get_user_email(user_id)
    
    get_jira_data = GetJiraData()
    email = get_jira_data.get_slack_email_to_jira_email(slack_email_to_register)

    request_jira_repository = RequestJiraRepository()
    request_jira_repository.issue_change_status(email, issue_key, status)

    say(f"✅ Jira課題 `{issue_key}` のステータスを{status}に変更しました。")

    jql_query = f"issue = \"{issue_key}\""
    jira_result = request_jira_repository.request_jql(jql_query)[0]
    block = request_jira_repository.format_jira_issue_for_slack(jira_result)
    
    client.chat_postMessage(
        channel=body["channel"]["id"],
        text=f"ステータスをTODOに変更",
        blocks=block
    )

    return