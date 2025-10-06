from scheduler.daily_reccomend.main import DailyTaskReccomendation
from scheduler.weekly_aggregate_award.main import WeeklyAggregateAward


def schedule_handler(data:dict, app, db):
    
    if "action" in data and data["action"] == "daily_reccomend_task":
        # ロジックをSchedulerTaskHandlerに委譲
        daily_task_reccomendation = DailyTaskReccomendation()
        result = daily_task_reccomendation.execute(app, db, data)
        print(result)

    elif "action" in data and data["action"] == "weekly_aggregate_award":
        # ロジックをWeeklyAggregateAwardHandlerに委譲
        weekly_aggregate_award = WeeklyAggregateAward()
        result = weekly_aggregate_award.execute(app, db, data)
        print(result)

    else:
        print("アクションフラグが設定されていないか、値が異なります。")