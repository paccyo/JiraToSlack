"""
Phase 3: コアデータ取得
スプリント内のサブタスクデータを取得し、親タスクとの関連付けを行う。
"""

import logging
from typing import List, Optional, Dict, Any

try:  # Prefer absolute for test monkeypatch compatibility
    from Loder.jira_client import JiraClient  # type: ignore
except Exception:  # pragma: no cover
    from ..Loder.jira_client import JiraClient  # type: ignore
from .types import (
    AuthContext,
    JiraMetadata,
    CoreData,
    TaskTotals,
    SubtaskData,
    ParentTask,
)


logger = logging.getLogger(__name__)


class CoreDataError(Exception):
    """コアデータ取得時のエラー"""
    pass


def fetch_core_data(
    auth: AuthContext,
    metadata: JiraMetadata,
    enable_logging: bool = False
) -> CoreData:
    """
    スプリント内のサブタスクデータを取得する。
    
    Args:
        auth: 認証コンテキスト
        metadata: Jiraメタデータ
        enable_logging: ログ出力を有効化するかどうか
    
    Returns:
        CoreData: 取得したコアデータ
    
    Raises:
        CoreDataError: データ取得に失敗した場合
    """
    if enable_logging:
        logger.info("Phase 3: コアデータ取得を開始します")
    
    try:
        client = JiraClient()
        
        # スプリント内の親タスク（サブタスクを持つもの）を取得
        sprint_id = metadata.sprint.sprint_id
        project_key = metadata.project_key
        
        if enable_logging:
            logger.info(f"スプリントID {sprint_id} の課題を取得します")
        
        # 親タスクのみを取得（サブタスク以外）
        fields = ["summary", "issuetype", "status", "subtasks", "assignee"]
        code, parent_issues, error = _fetch_parent_tasks(
            client, 
            sprint_id, 
            project_key, 
            fields
        )
        
        if code != 200 or parent_issues is None:
            raise CoreDataError(f"親タスク取得に失敗しました: {error}")
        
        if enable_logging:
            logger.info(f"親タスク {len(parent_issues)} 件を取得しました")
        
        # サブタスクの詳細情報を取得
        parents_with_subtasks: List[ParentTask] = []
        total_subtasks = 0
        total_done = 0
        
        for parent_issue in parent_issues:
            parent_data = _extract_parent_task(
                client,
                parent_issue,
                metadata.story_points_field,
                enable_logging
            )
            
            if parent_data and parent_data.subtasks:
                parents_with_subtasks.append(parent_data)
                total_subtasks += len(parent_data.subtasks)
                total_done += sum(1 for sub in parent_data.subtasks if sub.is_done)
        
        if enable_logging:
            logger.info(
                f"サブタスク処理完了: 合計 {total_subtasks} 件、"
                f"完了 {total_done} 件 ({int(total_done/max(1,total_subtasks)*100)}%)"
            )
        
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
        
        if enable_logging:
            logger.info("Phase 3: コアデータ取得が完了しました")
        
        return core_data
        
    except CoreDataError:
        raise
    except Exception as e:
        raise CoreDataError(f"予期しないエラーが発生しました: {str(e)}") from e


def _fetch_parent_tasks(
    client: JiraClient,
    sprint_id: int,
    project_key: Optional[str],
    fields: List[str]
) -> tuple[int, Optional[List[Dict[str, Any]]], str]:
    """
    スプリント内の親タスクを取得する（Agile API使用）。
    
    Args:
        client: JiraClient
        sprint_id: スプリントID
        project_key: プロジェクトキー（オプション）
        fields: 取得するフィールドのリスト
    
    Returns:
        (status_code, issues, error_message)
    """
    # Agile APIでスプリント内の課題を取得
    # サブタスク以外（親タスク）のみを対象とする
    start_at = 0
    batch_size = 100
    all_issues: List[Dict[str, Any]] = []
    
    # JQLクエリ: サブタスク以外のタスクを取得
    jql_parts = ["type not in subTaskIssueTypes()"]
    if project_key:
        jql_parts.insert(0, f"project={project_key}")
    jql = " AND ".join(jql_parts)
    
    while True:
        params = {
            "jql": jql,
            "fields": ",".join(fields),
            "startAt": start_at,
            "maxResults": batch_size,
        }
        
        code, data, err = client.api_get(
            f"{client.domain}/rest/agile/1.0/sprint/{sprint_id}/issue",
            params=params
        )
        
        if code != 200 or not data:
            return code, None, f"スプリント {sprint_id} の課題取得に失敗: {err}"
        
        issues = data.get("issues", [])
        total = int(data.get("total", 0))
        all_issues.extend(issues)
        
        start_at += len(issues)
        if start_at >= total or not issues:
            break
    
    return 200, all_issues, ""


def _extract_parent_task(
    client: JiraClient,
    parent_issue: Dict[str, Any],
    story_points_field: str,
    enable_logging: bool
) -> Optional[ParentTask]:
    """
    親タスクからParentTaskオブジェクトを抽出する。
    
    Args:
        client: JiraClient
        parent_issue: 親タスクのJSONデータ
        story_points_field: ストーリーポイントフィールドID
        enable_logging: ログ出力を有効化するかどうか
    
    Returns:
        ParentTask または None（サブタスクがない場合）
    """
    fields = parent_issue.get("fields", {})
    subtasks = fields.get("subtasks", [])
    
    # サブタスクがない場合はスキップ
    if not subtasks:
        return None
    
    parent_key = parent_issue.get("key", "")
    parent_summary = fields.get("summary", "")
    parent_assignee = (fields.get("assignee") or {}).get("displayName")
    
    # サブタスクの詳細を取得
    subtask_list: List[SubtaskData] = []
    
    for subtask_raw in subtasks:
        subtask_data = _extract_subtask_data(
            client,
            subtask_raw,
            parent_assignee,
            story_points_field
        )
        
        if subtask_data:
            subtask_list.append(subtask_data)
    
    if not subtask_list:
        return None
    
    return ParentTask(
        key=parent_key,
        summary=parent_summary,
        assignee=parent_assignee,
        subtasks=subtask_list
    )


def _extract_subtask_data(
    client: JiraClient,
    subtask_raw: Dict[str, Any],
    parent_assignee: Optional[str],
    story_points_field: str
) -> Optional[SubtaskData]:
    """
    サブタスクの詳細情報を取得してSubtaskDataオブジェクトを作成する。
    
    Args:
        client: JiraClient
        subtask_raw: サブタスクの基本情報
        parent_assignee: 親タスクの担当者
        story_points_field: ストーリーポイントフィールドID
    
    Returns:
        SubtaskData または None（取得失敗時）
    """
    subtask_id = subtask_raw.get("id") or subtask_raw.get("key")
    if not subtask_id:
        return None
    
    # サブタスクの詳細を取得
    query_fields = [
        "summary",
        "status",
        "assignee",
        "issuetype",
        "created",
        "resolutiondate",
        story_points_field,
    ]
    
    params = {
        "fields": ",".join(query_fields),
        "expand": "changelog"
    }
    
    url = f"{client.domain}/rest/api/3/issue/{subtask_id}"
    code, data, error = client.api_get(url, params=params)
    
    if code != 200 or not data:
        logger.warning(f"サブタスク {subtask_id} の詳細取得に失敗: {error}")
        return None
    
    fields = data.get("fields", {})
    
    # 基本情報
    key = data.get("key", subtask_id)
    summary = fields.get("summary", "")
    status = fields.get("status", {})
    status_name = status.get("name", "")
    
    # 完了判定
    is_done = _is_status_done(status)
    
    # 担当者
    assignee = (fields.get("assignee") or {}).get("displayName") or parent_assignee
    
    # ストーリーポイント
    sp_raw = fields.get(story_points_field)
    story_points = float(sp_raw) if isinstance(sp_raw, (int, float)) else 1.0
    
    # 日時情報
    created = fields.get("created")
    resolution_date = fields.get("resolutiondate")
    
    # changelogから開始時刻と完了時刻を抽出
    changelog = data.get("changelog", {})
    started_at, completed_at = _extract_times_from_changelog(changelog)
    
    # 完了時刻がない場合はresolution_dateを使用
    if not completed_at and resolution_date:
        completed_at = resolution_date
    
    return SubtaskData(
        key=key,
        summary=summary,
        status=status_name,
        done=is_done,
        assignee=assignee,
        story_points=story_points,
        created=created,
        started_at=started_at,
        completed_at=completed_at
    )


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
    
    histories = changelog.get("histories", [])
    if not histories:
        return None, None
    
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
