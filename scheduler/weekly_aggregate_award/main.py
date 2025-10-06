from datetime import datetime, timedelta
from util.request_jira import RequestJiraRepository
from util.get_slack_data import GetSlackData


class WeeklyAggregateAward:
    def execute(self, app, db, message_data):
        """
        Firestoreから全ユーザーを取得し、先週完了したタスクを集計する
        """
        # Firestoreから全ユーザーを取得
        users_ref = db.collection('slack_users').stream()

        jira_repo = RequestJiraRepository()
        
        weekly_completed_tasks = {}

        # NOTE: 'customfield_10016' はJiraのストーリーポイントのカスタムフィールドIDです。
        # ご利用のJira環境に合わせてIDを変更してください。
        story_point_field_id = 'customfield_10016'

        for user_doc in users_ref:
            user_data = user_doc.to_dict()
            user_email = user_data.get("jira_email")

            if not user_email:
                continue

            # 先週完了したタスクを取得するJQL
            jql_query = (
                f'assignee = "{user_email}" AND '
                f'status = "完了" AND '
                f'resolved >= startOfWeek(-1) AND resolved <= endOfWeek(-1)'
            )

            # JQLを実行して課題を検索
            searched_issues = jira_repo.request_jql(jql_query)

            total_completed = 0
            on_time_completed = 0
            total_story_points = 0
            completed_by_size = {}

            if searched_issues:
                total_completed = len(searched_issues)
                for issue in searched_issues:
                    # 期日内完了のチェック
                    due_date_str = issue.fields.duedate
                    resolution_date_str = issue.fields.resolutiondate
                    if due_date_str and resolution_date_str:
                        resolution_date = datetime.strptime(resolution_date_str, '%Y-%m-%dT%H:%M:%S.%f%z').date()
                        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                        if resolution_date <= due_date:
                            on_time_completed += 1
                    
                    # ストーリーポイントの集計
                    story_points = getattr(issue.fields, story_point_field_id, None)
                    if isinstance(story_points, (int, float)):
                        total_story_points += story_points
                    
                    # タスクサイズごとの集計
                    size_key = str(story_points) if story_points is not None else 'None'
                    completed_by_size[size_key] = completed_by_size.get(size_key, 0) + 1

            weekly_completed_tasks[user_email] = {
                'total': total_completed,
                'on_time': on_time_completed,
                'total_story_points': total_story_points,
                'by_size': completed_by_size
            }
        
        # 集計結果を合計完了数が多い順にソート
        sorted_users = sorted(weekly_completed_tasks.items(), key=lambda item: item[1]['total'], reverse=True)

        # Slack Blockを作成
        formated_blocks = self.aggregate_award_formated_slack_blocks(sorted_users)

        # Blockをコンソールに出力（デバッグ用）
        import json
        print(json.dumps(formated_blocks, indent=4, ensure_ascii=False))

        get_slack_data = GetSlackData()

        channel_id = get_slack_data.get_channel_id("general")


        # 取得したユーザーIDを 'channel' に指定してDMを送信
        app.client.chat_postMessage(
            channel=channel_id,
            text="タスク集計結果",
            blocks=formated_blocks
        )

        return


    def aggregate_award_formated_slack_blocks(self, sorted_users):
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🏆 Weekly Task Champions 🏆",
                    "emoji": True
                }
            }
        ]

        ranking_emojis = ["🥇", "🥈", "🥉"]
        rank_suffixes = {1: "st", 2: "nd", 3: "rd"}

        for i, (email, stats) in enumerate(sorted_users):
            rank = i + 1
            if rank <= 3:
                suffix = rank_suffixes.get(rank, "th")
                rank_str = f"{ranking_emojis[i]} *{rank}{suffix} Place:*"
            else:
                rank_str = f"*{rank}th Place:*"

            blocks.append({"type": "divider"})

            # ユーザーランクと名前
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{rank_str}\n`{email}`"
                }
            })

            # 詳細な統計情報
            fields = [
                {"type": "mrkdwn", "text": f"*Total Completed:*\n{stats['total']} tasks"},
                {"type": "mrkdwn", "text": f"*Total Story Points:*\n{stats['total_story_points']}"},
                {"type": "mrkdwn", "text": f"*On-Time Completion:*\n{stats['on_time']}/{stats['total']}"}
            ]
            blocks.append({
                "type": "section",
                "fields": fields
            })

            # ストーリーポイントの内訳
            if stats['by_size']:
                breakdown_text = "*Breakdown by Size:*\n"
                sorted_sizes = sorted(stats['by_size'].items(), key=lambda item: str(item[0]))
                for size, count in sorted_sizes:
                    breakdown_text += f"- `{size}` points: {count} task(s)\n"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": breakdown_text
                    }
                })

        return blocks

