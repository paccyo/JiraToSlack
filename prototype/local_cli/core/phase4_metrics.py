"""
Phase 4: メトリクス収集
複数のJQLクエリを並列実行してメトリクスを収集する。
"""

import logging
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

if TYPE_CHECKING:
    from Loder.jira_client import JiraClient

from .types import AuthContext, JiraMetadata, CoreData, MetricsCollection


logger = logging.getLogger(__name__)


class MetricsError(Exception):
    """メトリクス収集時のエラー"""
    pass


@dataclass
class MetricQuery:
    """メトリクスクエリの定義"""
    name: str
    jql: str
    description: str


def collect_metrics(
    auth: AuthContext,
    metadata: JiraMetadata,
    core_data: CoreData,
    enable_logging: bool = False
) -> MetricsCollection:
    """
    各種メトリクスを並列で収集する。
    
    Args:
        auth: 認証コンテキスト
        metadata: Jiraメタデータ
        core_data: コアデータ
        enable_logging: ログ出力を有効化するかどうか
    
    Returns:
        MetricsCollection: 収集したメトリクス
    
    Raises:
        MetricsError: メトリクス収集に失敗した場合
    """
    if enable_logging:
        logger.info("Phase 4: メトリクス収集を開始します")
    
    try:
        from Loder.jira_client import JiraClient
        client = JiraClient()
        sprint_id = metadata.sprint.sprint_id
        project_key = metadata.project_key
        
        # メトリクスクエリを定義
        queries = _build_metric_queries(sprint_id, project_key)
        
        if enable_logging:
            logger.info(f"{len(queries)} 個のメトリクスクエリを並列実行します")
        
        # 並列実行
        results = _execute_queries_parallel(client, queries, enable_logging)
        
        # 結果を集約
        metrics = _aggregate_metrics(results, core_data)
        
        if enable_logging:
            logger.info("Phase 4: メトリクス収集が完了しました")
            logger.info(f"収集したメトリクス: {len(results)} 件")
        
        return metrics
        
    except MetricsError:
        raise
    except Exception as e:
        raise MetricsError(f"予期しないエラーが発生しました: {str(e)}") from e


def _build_metric_queries(
    sprint_id: int,
    project_key: str
) -> List[MetricQuery]:
    """
    メトリクスクエリのリストを構築する。
    
    Args:
        sprint_id: スプリントID
        project_key: プロジェクトキー
    
    Returns:
        List[MetricQuery]: クエリのリスト
    """
    import os
    
    # 高優先度のタスク
    high_priorities = os.getenv("HIGH_PRIORITIES", "Highest,High")
    pri_list = ",".join([f'"{p.strip()}"' for p in high_priorities.split(",") if p.strip()])
    
    # 期限間近の日数
    due_soon_days_raw = os.getenv("DUE_SOON_DAYS", "7")
    try:
        due_soon_days_val = int(due_soon_days_raw)
    except (TypeError, ValueError):
        logger.warning("DUE_SOON_DAYS の値 '%s' を整数に変換できませんでした。デフォルトの 7 を使用します", due_soon_days_raw)
        due_soon_days_val = 7

    if due_soon_days_val > 0:
        due_soon_offset = f"+{due_soon_days_val}d"
    elif due_soon_days_val < 0:
        due_soon_offset = f"{due_soon_days_val}d"
    else:
        due_soon_offset = "0d"
    
    queries = [
        # 1. 期限切れサブタスク
        MetricQuery(
            name="overdue",
            jql=f"Sprint={sprint_id} AND type in subTaskIssueTypes() AND duedate < endOfDay() AND statusCategory != \"Done\"",
            description="期限切れのサブタスク"
        ),
        
        # 2. 期限間近サブタスク
        MetricQuery(
            name="due_soon",
            jql=(
                "Sprint={sprint_id} AND type in subTaskIssueTypes() AND "
                "duedate >= startOfDay() AND "
                "duedate <= endOfDay(\"{offset}\") AND "
                "statusCategory != \"Done\""
            ).format(sprint_id=sprint_id, offset=due_soon_offset),
            description="期限間近のサブタスク"
        ),
        
        # 3. 高優先度の未着手サブタスク
        MetricQuery(
            name="high_priority_todo",
            jql=f"Sprint={sprint_id} AND type in subTaskIssueTypes() AND priority in ({pri_list}) AND statusCategory = \"To Do\"",
            description="高優先度の未着手サブタスク"
        ),
        
        # 4. 未割り当てサブタスク
        MetricQuery(
            name="unassigned",
            jql=f"Sprint={sprint_id} AND type in subTaskIssueTypes() AND assignee is EMPTY AND statusCategory != \"Done\"",
            description="未割り当てのサブタスク"
        ),
        
        # 5. プロジェクト全体のサブタスク数
        MetricQuery(
            name="project_total",
            jql=f"project={project_key} AND type in subTaskIssueTypes()",
            description="プロジェクト全体のサブタスク数"
        ),
        
        # 6. プロジェクトの未完了サブタスク数
        MetricQuery(
            name="project_open",
            jql=f"project={project_key} AND type in subTaskIssueTypes() AND statusCategory != \"Done\"",
            description="プロジェクトの未完了サブタスク数"
        ),
    ]
    
    return queries


def _execute_queries_parallel(
    client: "JiraClient",
    queries: List[MetricQuery],
    enable_logging: bool
) -> Dict[str, int]:
    """
    クエリを並列実行してカウントを取得する。
    
    Args:
        client: JiraClient
        queries: クエリのリスト
        enable_logging: ログ出力を有効化するかどうか
    
    Returns:
        Dict[str, int]: クエリ名 -> カウント のマップ
    """
    results: Dict[str, int] = {}
    
    # ThreadPoolExecutorで並列実行（最大6並列）
    with ThreadPoolExecutor(max_workers=6) as executor:
        # 各クエリを並列実行
        future_to_query = {
            executor.submit(_execute_single_query, client, query): query
            for query in queries
        }
        
        # 結果を収集
        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                count = future.result()
                results[query.name] = count
                
                if enable_logging:
                    logger.info(f"  {query.description}: {count} 件")
                    
            except Exception as e:
                logger.warning(f"クエリ '{query.name}' の実行に失敗: {e}")
                results[query.name] = 0
    
    return results


def _execute_single_query(
    client: "JiraClient",
    query: MetricQuery
) -> int:
    """
    単一のクエリを実行してカウントを取得する。
    
    Args:
        client: JiraClient
        query: メトリクスクエリ
    
    Returns:
        int: カウント
    """
    # まずapproximate_countを試す
    code, count, error = client.count_jql(query.jql, batch=500)
    
    if code == 200 and count is not None:
        return count
    
    # 失敗した場合は0を返す
    logger.warning(f"クエリ実行失敗 ({query.name}): {error}")
    return 0


def _aggregate_metrics(
    query_results: Dict[str, int],
    core_data: CoreData
) -> MetricsCollection:
    """
    クエリ結果とコアデータからメトリクスを集約する。
    
    Args:
        query_results: クエリ結果
        core_data: コアデータ
    
    Returns:
        MetricsCollection: 集約されたメトリクス
    """
    # KPIデータ
    kpis = {
        "sprintTotal": core_data.totals.subtasks,
        "sprintDone": core_data.totals.done,
        "sprintOpen": core_data.totals.not_done,
        "projectTotal": query_results.get("project_total", 0),
        "projectOpenTotal": query_results.get("project_open", 0),
        "overdue": query_results.get("overdue", 0),
        "dueSoon": query_results.get("due_soon", 0),
        "highPriorityTodo": query_results.get("high_priority_todo", 0),
        "unassignedCount": query_results.get("unassigned", 0),
    }
    
    # リスクデータ
    risks = {
        "overdue": query_results.get("overdue", 0),
        "dueSoon": query_results.get("due_soon", 0),
        "highPriorityTodo": query_results.get("high_priority_todo", 0),
    }
    
    # 担当者別の集計
    assignee_workload = _calculate_assignee_workload(core_data)
    
    return MetricsCollection(
        kpis=kpis,
        risks=risks,
        assignee_workload=assignee_workload
    )


def _calculate_assignee_workload(core_data: CoreData) -> Dict[str, Dict[str, Any]]:
    """
    担当者別のワークロードを計算する。
    
    Args:
        core_data: コアデータ
    
    Returns:
        Dict[str, Dict[str, Any]]: 担当者名 -> ワークロード情報
    """
    workload: Dict[str, Dict[str, Any]] = {}
    
    for parent in core_data.parents:
        for subtask in parent.subtasks:
            assignee = subtask.assignee or "(未割り当て)"
            
            if assignee not in workload:
                workload[assignee] = {
                    "assignee": assignee,
                    "subtasks": 0,
                    "done": 0,
                    "storyPoints": 0.0,
                }
            
            workload[assignee]["subtasks"] += 1
            workload[assignee]["storyPoints"] += subtask.story_points
            
            if subtask.done:
                workload[assignee]["done"] += 1
    
    return workload
