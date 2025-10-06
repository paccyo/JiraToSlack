"""
Phase 4: メトリクス収集
複数のJQLクエリを並列実行してメトリクスを収集する。
"""

import logging
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

if TYPE_CHECKING:
    try:
        from Loder.jira_client import JiraClient  # type: ignore
    except Exception:  # pragma: no cover
        from ..Loder.jira_client import JiraClient  # type: ignore

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
        logger.info("[Phase 4] メトリクス収集を開始します")
    
    try:
        try:
            from Loder.jira_client import JiraClient  # type: ignore
        except Exception:  # pragma: no cover
            from ..Loder.jira_client import JiraClient  # type: ignore
        client = JiraClient()
        sprint_id = metadata.sprint.sprint_id
        project_key = metadata.project_key
        
        # メトリクスクエリを定義
        queries = _build_metric_queries(sprint_id, project_key)
        
        if enable_logging:
            logger.info(f"[Phase 4] {len(queries)} 個のメトリクスクエリを並列実行します")
        
        # 並列実行
        results = _execute_queries_parallel(client, queries, enable_logging)
        
        # 結果を集約
        metrics = _aggregate_metrics(results, core_data)

        # 追加: Velocity / Evidence (Burndown削除)
        # Velocity
        try:
            velocity = _calculate_velocity(core_data)
            metrics.velocity = velocity
        except Exception as ve:  # pragma: no cover
            logger.warning(f"Velocity計算でエラー: {ve}")

        # Historical Velocity
        try:
            import os
            hv_sample_limit_raw = os.getenv("HISTORICAL_VELOCITY_SAMPLE_LIMIT", "6")
            try:
                hv_sample_limit = max(1, min(20, int(hv_sample_limit_raw)))
            except ValueError:
                hv_sample_limit = 6
            hist = _calculate_historical_velocity(
                client,
                metadata.board.board_id,
                metadata.story_points_field,
                sample_limit=hv_sample_limit,
                enable_logging=enable_logging
            )
            if hist and metrics.velocity is not None:
                metrics.velocity["historical"] = hist
                if enable_logging:
                    logger.info(
                        f"[Phase 4] Historical Velocity: avgCompletedSP={hist['averageCompletedSP']} avgPlannedSP={hist.get('averagePlannedSP')} (samples={hist['sampleCount']})"
                    )
            elif enable_logging:
                logger.warning("[Phase 4] Historical Velocity: サンプルが取得できませんでした (フォールバック無効)")
        except Exception as hve:  # pragma: no cover
            logger.warning(f"Historical Velocity計算でエラー: {hve}")

        try:
            evidence = _extract_evidence(core_data, results, metadata, top_n=5)
            metrics.evidence = evidence
            if enable_logging and evidence:
                logger.info(f"[Phase 4] Evidence抽出 {len(evidence)} 件")
        except Exception as ee:  # pragma: no cover
            logger.warning(f"Evidence抽出でエラー: {ee}")
        
        if enable_logging:
            logger.info("[Phase 4] メトリクス収集が完了しました")
            logger.info(f"[Phase 4] 収集したメトリクス: {len(results)} 件")
        
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


def _normalize_story_points(value: Any, default_if_missing: float = 1.0) -> float:
    """Story Points を正規化する。未設定(None/非数値)は default_if_missing を返す。"""
    sp: float
    if isinstance(value, (int, float)):
        sp = float(value)
    elif value is None:
        sp = default_if_missing
    else:
        try:
            sp = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            sp = default_if_missing
    if sp < 0:
        return 0.0
    return sp


def _fetch_sprint_issues(
    client: "JiraClient",
    sprint_id: int,
    story_points_field: str,
    batch: int = 100,
) -> tuple[int, List[Dict[str, Any]], str]:
    """Agile API を用いてスプリント内の課題一覧を取得する。"""
    all_issues: List[Dict[str, Any]] = []
    start_at = 0
    last_error = ""
    while True:
        params = {
            "startAt": start_at,
            "maxResults": batch,
            "fields": f"status,{story_points_field}",
        }
        code, data, err = client.api_get(
            f"{client.domain}/rest/agile/1.0/sprint/{sprint_id}/issue",
            params=params,
        )
        if code != 200 or not isinstance(data, dict):
            return code, all_issues, err
        issues = data.get("issues") or []
        all_issues.extend(issues)
        total = data.get("total")
        if total is not None:
            if len(all_issues) >= total:
                break
        else:
            if not issues or len(issues) < batch:
                break
        start_at += batch
        last_error = err
    return 200, all_issues, last_error


def _calculate_velocity(core_data: CoreData) -> Dict[str, Any]:
    """Velocity(ストーリーポイント)を計算する。"""
    planned = 0.0
    completed = 0.0
    by_assignee: Dict[str, Dict[str, float]] = {}
    for parent in core_data.parents:
        for st in parent.subtasks:
            sp = _normalize_story_points(st.story_points)
            planned += sp
            assignee = st.assignee or "(未割り当て)"
            if assignee not in by_assignee:
                by_assignee[assignee] = {"plannedSP": 0.0, "completedSP": 0.0}
            by_assignee[assignee]["plannedSP"] += sp
            if st.done:
                completed += sp
                by_assignee[assignee]["completedSP"] += sp
    completion_rate = completed / planned if planned > 0 else 0.0
    return {
        "plannedSP": round(planned, 2),
        "completedSP": round(completed, 2),
        "completionRate": completion_rate,
        "byAssignee": {
            k: {
                "plannedSP": round(v["plannedSP"], 2),
                "completedSP": round(v["completedSP"], 2),
                "completionRate": (v["completedSP"] / v["plannedSP"] if v["plannedSP"] > 0 else 0.0)
            }
            for k, v in by_assignee.items()
        }
    }


## Burndown機能は削除されました（_calculate_burndown 関数は存在しません）


def _extract_evidence(core_data: CoreData, query_results: Dict[str, int], metadata: JiraMetadata, top_n: int = 5) -> Optional[List[Dict[str, Any]]]:
    """重要エビデンスを抽出（簡易版）。"""
    evidence: List[Dict[str, Any]] = []
    # 高優先度未完了
    high_priority_set = {p.strip().lower() for p in (metadata.project_key and ["Highest", "High"] or ["High"]) if p}
    for parent in core_data.parents:
        for st in parent.subtasks:
            if st.done:
                continue
            if st.priority and st.priority.strip().lower() in {"highest", "high"}:
                evidence.append({
                    "type": "highPriorityNotDone",
                    "key": st.key,
                    "summary": st.summary,
                    "priority": st.priority,
                    "assignee": st.assignee or "(未割り当て)"
                })
    # 未割り当て
    for parent in core_data.parents:
        for st in parent.subtasks:
            if st.done:
                continue
            if not st.assignee:
                evidence.append({
                    "type": "unassigned",
                    "key": st.key,
                    "summary": st.summary,
                    "priority": st.priority,
                    "assignee": "(未割り当て)"
                })
    # 重複除去 (key,type) 単位
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for item in evidence:
        sig = (item["type"], item["key"])
        if sig in seen:
            continue
        seen.add(sig)
        uniq.append(item)
    if not uniq:
        return None
    return uniq[:top_n]


def _calculate_historical_velocity(
    client: "JiraClient",
    board_id: int,
    story_points_field: str,
    sample_limit: int = 6,
    enable_logging: bool = False,
) -> Optional[Dict[str, Any]]:
    """プロジェクト内の全ての閉鎖済みスプリントを対象に、各スプリントの合計SP(全課題)と完了SPを集計し平均を算出する。

    要件: フォールバックなし・サブタスク限定なし・純粋な closed sprint の平均。
    出力: averageCompletedSP / averagePlannedSP / samples[{sprintId,name,completedSP,plannedSP,rate}]
    """

    def _is_done(status_field: Optional[Dict[str, Any]]) -> bool:
        if not status_field:
            return False
        cat = (status_field or {}).get("statusCategory") or {}
        return cat.get("key") == "done"

    try:
        if enable_logging:
            logger.info("[Phase 4] Historical Velocity(ALL issues) 取得開始 board_id=%s sample_limit=%s", board_id, sample_limit)
        code, data, err = client.api_get(
            f"{client.domain}/rest/agile/1.0/board/{board_id}/sprint",
            params={"state": "closed", "maxResults": 200},
        )
        if code != 200 or not data:
            if enable_logging:
                logger.warning("[Phase 4] Closed sprint list取得失敗 code=%s err=%s", code, err)
            return None
        values = data.get("values") or []
        if not values:
            if enable_logging:
                logger.warning("[Phase 4] Closed sprint 0件")
            return None
        # 完了日時降順
        try:
            values.sort(key=lambda v: v.get("completeDate") or v.get("endDate") or "", reverse=True)
        except Exception as se:
            if enable_logging:
                logger.warning("[Phase 4] sprint sort error: %s", se)
        samples: List[Dict[str, Any]] = []
        for idx, sp in enumerate(values):
            if len(samples) >= sample_limit:
                break
            sid = sp.get("id")
            if sid is None:
                continue
            sname = sp.get("name")
            comp = sp.get("completeDate") or sp.get("endDate")
            if enable_logging:
                logger.info("[Phase 4] Sprint集計開始 id=%s name=%s complete=%s", sid, sname, comp)
            fetch_code, issues, fetch_err = _fetch_sprint_issues(client, sid, story_points_field, batch=100)
            if fetch_code != 200:
                if enable_logging:
                    logger.warning("[Phase 4] Sprint id=%s Agile API取得失敗 code=%s err=%s -> search fallback", sid, fetch_code, fetch_err)
                fallback_jql = f"Sprint={sid}"
                fetch_code, issues, fetch_err = client.search_paginated(fallback_jql, ["status", story_points_field], batch=200)
            if fetch_code != 200:
                if enable_logging:
                    logger.warning("[Phase 4] Sprint id=%s 課題取得失敗 code=%s err=%s", sid, fetch_code, fetch_err)
                continue
            planned = 0.0
            completed = 0.0
            for issue in issues:
                flds = (issue or {}).get("fields", {})
                sp_raw = flds.get(story_points_field)
                sp_val = _normalize_story_points(sp_raw)
                planned += sp_val
                if _is_done(flds.get("status")):
                    completed += sp_val
            if planned == 0 and completed == 0:
                if enable_logging:
                    logger.info("[Phase 4] Sprint id=%s 課題0件 -> サンプル除外 (issues=%d)", sid, len(issues))
                continue
            rate = (completed / planned) if planned > 0 else 0.0
            sample = {
                "sprintId": sid,
                "name": sname,
                "plannedSP": round(planned, 2),
                "completedSP": round(completed, 2),
                "rate": rate,
            }
            samples.append(sample)
            if enable_logging:
                logger.info("[Phase 4] Sprint集計完了 id=%s planned=%.2f completed=%.2f rate=%.1f%%", sid, sample["plannedSP"], sample["completedSP"], rate*100)
        if not samples:
            if enable_logging:
                logger.warning("[Phase 4] Historical Velocity: 有効サンプル0件 (全closed sprint SP=0?)")
            return None
        avg_completed = sum(s["completedSP"] for s in samples) / len(samples)
        avg_planned = sum(s["plannedSP"] for s in samples) / len(samples)
        result = {
            "sampleCount": len(samples),
            "averageCompletedSP": round(avg_completed, 2),
            "averagePlannedSP": round(avg_planned, 2),
            "samples": samples,
        }
        if enable_logging:
            logger.info(
                "[Phase 4] Historical Velocity集計完了 sampleCount=%d averageCompletedSP=%.2f averagePlannedSP=%.2f", result["sampleCount"], result["averageCompletedSP"], result["averagePlannedSP"]
            )
        return result
    except Exception as e:  # pragma: no cover
        logger.warning("Historical velocity計算失敗: %s", e)
        return None


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
            workload[assignee]["storyPoints"] += _normalize_story_points(subtask.story_points)
            
            if subtask.done:
                workload[assignee]["done"] += 1
    
    return workload
