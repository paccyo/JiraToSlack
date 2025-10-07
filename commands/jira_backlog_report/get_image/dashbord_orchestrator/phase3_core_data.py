"""
Phase 3: コアデータ取得
スプリント内のサブタスクデータを取得し、親タスクとの関連付けを行う。
"""

import logging
from typing import List, Optional, Dict, Any


from commands.jira_backlog_report.get_image.dashbord_orchestrator.types import (
    JiraMetadata,
    CoreData,
    TaskTotals,
    SubtaskData,
    ParentTask,
)

from util.request_jira import RequestJiraRepository




class CoreDataError(Exception):
    """コアデータ取得時のエラー"""
    pass


def fetch_core_data(
    metadata: JiraMetadata,
) -> CoreData:
    # """
    # スプリント内のサブタスクデータを取得する。
    
    # Args:
    #     auth: 認証コンテキスト
    #     metadata: Jiraメタデータ
    #     enable_logging: ログ出力を有効化するかどうか
    
    # Returns:
    #     CoreData: 取得したコアデータ
    
    # Raises:
    #     CoreDataError: データ取得に失敗した場合
    # """
    # if enable_logging:
    #     print("[Phase 3] コアデータ取得を開始します")
    
    # try:
        
        # スプリント内の親タスク（サブタスクを持つもの）を取得
        sprint_id = metadata.sprint.get("id")
        project_key = metadata.project_key
        
        # if enable_logging:
        #     print(f"[Phase 3] スプリントID {sprint_id} の課題を取得します")
        
        # 親タスクのみを取得（サブタスク以外）
        # fields = ["summary", "issuetype", "status", "subtasks", "assignee"]
        # code, parent_issues, error = _fetch_parent_tasks(
        #     client, 
        #     sprint_id, 
        #     project_key, 
        #     fields
        # )
        jql_query = f"sprint = {sprint_id} AND type not in subTaskIssueTypes()"
        fields = ["summary", "issuetype", "status", "subtasks", "assignee"]
        request_jira_repository = RequestJiraRepository()
        searched_issues = request_jira_repository.request_jql(jql_query, fields=fields)
        # print(searched_issues)
        # searched_result = searched_issues[0].raw.get("issues", [])
        
        # if code != 200 or parent_issues is None:
        #     raise CoreDataError(f"親タスク取得に失敗しました: {error}")
        
        # if enable_logging:
        #     print(f"[Phase 3] 親タスク {len(parent_issues)} 件を取得しました")
        
        # サブタスクの詳細情報を取得
        parents_with_subtasks: List[ParentTask] = []
        total_subtasks = 0
        total_done = 0
        
        for issue in searched_issues:
            # parent_issue = issue.raw.get("issues", [])
            parent_issue = issue.raw
            fields = parent_issue.get("fields", {})
            subtasks = fields.get("subtasks", [])
            # サブタスクがなければ処理を終了
            if not subtasks:
                continue

            parent_key = parent_issue.get("key", "")
            parent_summary = fields.get("summary", "")
            parent_assignee = (fields.get("assignee") or {}).get("displayName")
            
            # try:
            subtask_list = []
            for subtask_raw in subtasks:
                subtask_id = subtask_raw.get("id") or subtask_raw.get("key")
                query_fields = [
                    "summary",
                    "status",
                    "assignee",
                    "issuetype",
                    "created",
                    "resolutiondate",
                    "priority",
                    "duedate",
                    metadata.story_points_field,
                ]
                subtask = request_jira_repository.get_issue(subtask_id, fields=query_fields,expand="changelog")
                subtask_issue = subtask.raw
                # print(subtask_issue)
                subtask_fields = subtask_issue.get("fields", {})
                subtask_key = subtask_issue.get("key", subtask_id)
                subtask_summary = subtask_fields.get("summary", "")
                subtask_status = subtask_fields.get("status", {})
                subtask_status_name = subtask_status.get("name", "")
                # 完了判定
                subtask_is_done = _is_status_done(subtask_status)
                subtasks_changelog = subtask_issue.get("changelog", {}).get("histories", [])
                started_at, completed_at = _extract_times_from_changelog(subtasks_changelog)

                
                # 担当者
                subtask_assignee = (subtask_fields.get("assignee") or {}).get("displayName") or parent_assignee
                
                # ストーリーポイント
                subtask_sp_raw = subtask_fields.get(metadata.story_points_field)
                subtask_story_points = float(subtask_sp_raw) if isinstance(subtask_sp_raw, (int, float)) else 1.0
                # 日時情報
                subtask_created = subtask_fields.get("created")
                subtask_resolution_date = subtask_fields.get("resolutiondate")
                subtask_priority_name = (subtask_fields.get("priority") or {}).get("name")
                subtask_due_date = subtask_fields.get("duedate")
                # assignee_obj = getattr(subtask_fields, 'assignee', None)
                
                subtask_list.append(
                    SubtaskData(
                        key=subtask_key,
                        summary=subtask_summary,
                        status=subtask_status_name,
                        done=subtask_is_done,
                        assignee=subtask_assignee,
                        priority=subtask_priority_name,
                        story_points=subtask_story_points,
                        created=subtask_created,
                        started_at=started_at,
                        completed_at=completed_at,
                        due_date=subtask_due_date,
                    )
                )
            parent_assignee_obj = fields.get("assignee")
            # except Exception as e:
            #     print(f"エラーが発生しました: {e}")
            # print("aa",fields)
            parent_data = ParentTask(
                key=parent_issue.get("key", ""),
                summary=fields.get("summary", ""),
                assignee=parent_assignee_obj.get("displayName") if parent_assignee_obj else None,
                subtasks=subtask_list
            )
            
            
            if parent_data and parent_data.subtasks:
                parents_with_subtasks.append(parent_data)
                total_subtasks += len(parent_data.subtasks)
                total_done += sum(1 for sub in parent_data.subtasks if sub.is_done)
        
        # if enable_logging:
        #     print(
        #         f"[Phase 3] サブタスク処理完了: 合計 {total_subtasks} 件、"
        #         f"完了 {total_done} 件 ({int(total_done/max(1,total_subtasks)*100)}%)"
        #     )
        
        # TaskTotalsを作成
        task_totals = TaskTotals(
            subtasks=total_subtasks,
            done=total_done,
            not_done=total_subtasks - total_done
        )
        
        # CoreDataを作成
        core_data = CoreData(
            parents=parents_with_subtasks,
            totals=task_totals
        )
        
        # if enable_logging:
        #     print("[Phase 3] コアデータ取得が完了しました")
        
        return core_data
        
    # except CoreDataError:
    #     raise
    # except Exception as e:
    #     raise CoreDataError(f"予期しないエラーが発生しました: {str(e)}") from e


def _is_status_done(status: Optional[Dict[str, Any]]) -> bool:
    """
    ステータスが完了状態かどうかを判定する。
    
    Args:
        status: ステータスフィールド
    
    Returns:
        完了状態ならTrue
    """
    if not status:
        return False
    
    category = status.get("statusCategory", {})
    key = category.get("key", "")
    
    return key == "done"

def _extract_times_from_changelog(
    changelog: Dict[str, Any]
) -> tuple[Optional[str], Optional[str]]:
    """
    changelogから開始時刻と完了時刻を抽出する。
    
    Args:
        changelog: Jira APIのchangelogデータ
    
    Returns:
        (started_at, completed_at) のタプル
    """
    if not changelog:
        return None, None
    
    histories = changelog
    # print(changelog)

    # print(len(changelog))
    # histories = changelog.get("histories", [])
    # if not histories:
    #     return None, None
    
    # 作成日時でソート
    try:
        histories.sort(key=lambda h: h.get("created", ""))
    except Exception:
        pass
    
    # 開始状態と完了状態を定義
    start_statuses = {
        "in progress", "in_progress", "doing", "進行中", "作業中", "対応中",
        "in review", "review", "レビュー", "qa"
    }
    
    done_statuses = {
        "done", "closed", "resolved", "完了"
    }
    
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    for history in histories:
        items = history.get("items", [])
        
        for item in items:
            if (item.get("field") or "").lower() != "status":
                continue
            
            to_status = str(item.get("toString", "")).strip().lower()
            to_status_normalized = to_status.replace(" ", "_").replace("-", "_")
            timestamp = history.get("created")
            
            # 開始時刻の判定
            if not started_at:
                if to_status_normalized in start_statuses or to_status in start_statuses:
                    started_at = timestamp
            
            # 完了時刻の判定
            if not completed_at:
                if to_status_normalized in done_statuses or to_status in done_statuses:
                    completed_at = timestamp
            
            if started_at and completed_at:
                break
        
        if started_at and completed_at:
            break
    
    return started_at, completed_at