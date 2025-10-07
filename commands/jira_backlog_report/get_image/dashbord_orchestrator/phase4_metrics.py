"""
Phase 4: メトリクス収集
複数のJQLクエリを並列実行してメトリクスを収集する。
"""

import logging
import os
from datetime import datetime, timedelta, timezone, date
from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass


from util.request_jira import RequestJiraRepository
from commands.jira_backlog_report.get_image.dashbord_orchestrator.types import AuthContext, JiraMetadata, CoreData, MetricsCollection


logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))


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
    metadata: JiraMetadata,
    core_data: CoreData,
) -> MetricsCollection:
    # """
    # 各種メトリクスを並列で収集する。
    
    # Args:
    #     auth: 認証コンテキスト
    #     metadata: Jiraメタデータ
    #     core_data: コアデータ
    #     enable_logging: ログ出力を有効化するかどうか
    
    # Returns:
    #     MetricsCollection: 収集したメトリクス
    
    # Raises:
    #     MetricsError: メトリクス収集に失敗した場合
    # """
    
    # try:

        # print(metadata.sprint)
        sprint_id = metadata.sprint["id"]
        project_key = metadata.project_key
        
        # メトリクスクエリを定義
        queries = _build_metric_queries(sprint_id, project_key)

        
        # 並列実行
        results = _execute_queries_parallel(queries)
        
        # 結果を集約
        metrics = _aggregate_metrics(results, core_data)

        # Time-in-Status (cycle time) 計算
        # try:
        scope = os.getenv("TIS_SCOPE", "sprint")
        unit = os.getenv("TIS_UNIT", "days")
        
        print(
            "[Phase 4] Time-in-status集計を開始 scope=%s unit=%s",
            scope,
            unit,
        )
        metrics.time_in_status = _calculate_time_in_status(
            metadata,
            unit=unit,
            scope=scope,
        )
        # print(metrics)
        if metrics.time_in_status:
            total_statuses = len(metrics.time_in_status.get("totalByStatus") or {})
            total_issues = len(metrics.time_in_status.get("perIssue") or [])
            print(
                "[Phase 4] Time-in-status集計完了 statuses=%s issues=%s",
                total_statuses,
                total_issues,
            )
        else:
            print("[Phase 4] Time-in-status集計結果: データが見つかりませんでした")
        # except Exception as tis_error:  # pragma: no cover - ログ目的
        #     print(f"Time-in-status計算でエラー: {tis_error}")

        # 追加: Velocity / Evidence (Burndown削除)
        # Velocity
        try:
            velocity = _calculate_velocity(core_data)
            metrics.velocity = velocity
        except Exception as ve:  # pragma: no cover
            print(f"Velocity計算でエラー: {ve}")

        # Historical Velocity
        try:
            hv_sample_limit_raw = os.getenv("HISTORICAL_VELOCITY_SAMPLE_LIMIT", "6")
            try:
                hv_sample_limit = max(1, min(20, int(hv_sample_limit_raw)))
            except ValueError:
                hv_sample_limit = 6
            hist = _calculate_historical_velocity(
                metadata.board["id"],
                metadata.story_points_field,
                sample_limit=hv_sample_limit,
            )
            if hist and metrics.velocity is not None:
                metrics.velocity["historical"] = hist
        except Exception as hve:  # pragma: no cover
            print(f"Historical Velocity計算でエラー: {hve}")

        try:
            evidence = _extract_evidence(core_data, results, metadata, top_n=5)
            metrics.evidence = evidence
            
        except Exception as ee:  # pragma: no cover
            print(f"Evidence抽出でエラー: {ee}")
        
        
        return metrics
        
    # except MetricsError:
    #     raise
    # except Exception as e:
    #     raise MetricsError(f"予期しないエラーが発生しました: {str(e)}") from e


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
    
    # 高優先度のタスク
    high_priorities = os.getenv("HIGH_PRIORITIES", "Highest,High")
    pri_list = ",".join([f'"{p.strip()}"' for p in high_priorities.split(",") if p.strip()])
    
    # 期限間近の日数
    due_soon_days_raw = os.getenv("DUE_SOON_DAYS", "7")
    try:
        due_soon_days_val = int(due_soon_days_raw)
    except (TypeError, ValueError):
        print("DUE_SOON_DAYS の値 '%s' を整数に変換できませんでした。デフォルトの 7 を使用します", due_soon_days_raw)
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
    queries: List[MetricQuery],
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
            executor.submit(_execute_single_query, query): query
            for query in queries
        }
        
        # 結果を収集
        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                count = future.result()
                results[query.name] = count
                
                print(f"  {query.description}: {count} 件")
                    
            except Exception as e:
                print(f"クエリ '{query.name}' の実行に失敗: {e}")
                results[query.name] = 0
    
    return results


def _execute_single_query(
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
    # code, count, error = client.count_jql(query.jql, batch=500)
    request_jira = RequestJiraRepository()
    issues = request_jira.request_jql(query=query.jql)

    count = issues.total
    
    if count is not None:
        return count
    
    # 失敗した場合は0を返す
    # print(f"クエリ実行失敗 ({query.name}): {error}")
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
    """重要エビデンスを抽出する。ダッシュボード/Markdown双方で見やすい情報を付与する。"""

    def _calc_age_days(created: Optional[str]) -> Optional[float]:
        if not created:
            return None
        dt = _parse_iso8601(created)
        if not dt:
            return None
        try:
            now = datetime.now(tz=JST)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc).astimezone(JST)
            else:
                dt = dt.astimezone(JST)
            delta = now - dt
            if delta.total_seconds() < 0:
                return 0.0
            return round(delta.total_seconds() / 86400, 1)
        except Exception:
            return None

    def _parse_due_date(raw: Optional[str]) -> Optional[date]:
        if not raw:
            return None
        try:
            if "T" in raw:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(JST).date()
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except Exception:
            try:
                return datetime.fromisoformat(raw).date()
            except Exception:
                return None

    def _calc_due_info(raw: Optional[str]) -> tuple[Optional[str], Optional[int], Optional[str]]:
        due_date_obj = _parse_due_date(raw)
        if not due_date_obj:
            return None, None, None
        today = datetime.now(tz=JST).date()
        delta_days = (due_date_obj - today).days
        if delta_days < 0:
            label = f"超過{abs(delta_days)}日"
            status = "overdue"
        elif delta_days == 0:
            label = "今日まで"
            status = "due_today"
        elif delta_days <= 3:
            label = f"あと{delta_days}日"
            status = "due_soon"
        else:
            label = due_date_obj.isoformat()
            status = "future"
        return label, delta_days, status

    def _build_reason(category: str, priority: Optional[str], assignee: Optional[str], days: Optional[float], due_label: Optional[str]) -> str:
        hints: List[str] = []
        hints.append(category)
        if priority:
            hints.append(f"優先度{priority}")
        if assignee:
            hints.append(f"担当: {assignee}")
        if isinstance(days, (int, float)):
            hints.append(f"滞留: {days:.1f}日")
        if due_label:
            hints.append(f"期限: {due_label}")
        summary = " / ".join(hints)
        return f"{summary}。早急に対応が必要です"

    def _category_for_type(item_type: str) -> str:
        if item_type == "highPriorityNotDone":
            return "高優先度未完了"
        if item_type == "unassigned":
            return "担当未設定"
        return "要注視"

    evidence: List[Dict[str, Any]] = []

    for parent in core_data.parents:
        for st in parent.subtasks:
            if st.done:
                continue

            days_open = _calc_age_days(st.created)
            status = st.status or "未設定"
            assignee = st.assignee or "(未割り当て)"
            due_raw = st.due_date
            due_label, due_in_days, due_status = _calc_due_info(due_raw)

            def _append(item_type: str) -> None:
                category = _category_for_type(item_type)
                reason_text = _build_reason(category, st.priority, assignee, days_open, due_label)
                evidence.append({
                    "type": item_type,
                    "category": category,
                    "key": st.key,
                    "summary": st.summary,
                    "priority": st.priority,
                    "assignee": assignee,
                    "status": status,
                    "days": days_open,
                    "due": due_raw,
                    "duedate": due_raw,
                    "dueLabel": due_label,
                    "dueInDays": due_in_days,
                    "dueStatus": due_status,
                    "why": reason_text,
                    "reason": reason_text,
                })

            if st.priority and st.priority.strip().lower() in {"highest", "high"}:
                _append("highPriorityNotDone")
            if not st.assignee:
                _append("unassigned")

    if not evidence:
        return None

    # 重複除去 (type, key)
    unique: Dict[tuple[str, str], Dict[str, Any]] = {}
    for item in evidence:
        sig = (item["type"], item["key"])
        if sig not in unique:
            unique[sig] = item

    ranked = list(unique.values())

    def _score(item: Dict[str, Any]) -> float:
        type_weight = 2 if item.get("type") == "highPriorityNotDone" else 1
        priority = str(item.get("priority") or "").lower()
        priority_weight = {
            "highest": 1.0,
            "high": 0.8,
            "medium": 0.4,
        }.get(priority, 0.2)
        days = item.get("days")
        days_weight = float(days) if isinstance(days, (int, float)) else 0.0
        return type_weight * 10 + priority_weight * 5 + days_weight

    ranked.sort(key=_score, reverse=True)

    limit = max(1, int(os.getenv("EVIDENCE_TOP_N", str(top_n))))
    return ranked[:limit]


def _calculate_historical_velocity(
    board_id: int,
    story_points_field: str,
    sample_limit: int = 6,
    enable_logging: bool = True,
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
            print("[Phase 4] Historical Velocity(ALL issues) 取得開始 board_id=%s sample_limit=%s", board_id, sample_limit)

        request_jira = RequestJiraRepository()
        data = request_jira.get_sprint(board_id=board_id, state="closed", maxResults=200)
        # print(data)
        if not data:
            if enable_logging:
                print("[Phase 4] Closed sprint list取得失敗")
            return None
        values = data
        if not values:
            if enable_logging:
                print("[Phase 4] Closed sprint 0件")
            return None
        # 完了日時降順
        try:
            values.sort(key=lambda v: v.completeDate or v.endDate or "", reverse=True)
        except Exception as se:
            if enable_logging:
                print("[Phase 4] sprint sort error: %s", se)
        samples: List[Dict[str, Any]] = []
        for idx, sp in enumerate(values):
            if len(samples) >= sample_limit:
                break
            sid = sp.id
            if sid is None:
                continue
            sname = sp.name
            comp = sp.completeDate or sp.endDate
            if enable_logging:
                print("[Phase 4] Sprint集計開始 id=%s name=%s complete=%s", sid, sname, comp)
            # fetch_code, issues, fetch_err = _fetch_sprint_issues(client, sid, story_points_field, batch=100)
            issues = request_jira.request_jql(query=f"Sprint={sid}", fields=story_points_field)
            # if fetch_code != 200:
                # if enable_logging:
                #     print("[Phase 4] Sprint id=%s Agile API取得失敗 code=%s err=%s -> search fallback", sid, fetch_code, fetch_err)
                # fallback_jql = f"Sprint={sid}"
                # fetch_code, issues, fetch_err = client.search_paginated(fallback_jql, ["status", story_points_field], batch=200)
            # if fetch_code != 200:
            #     if enable_logging:
            #         print("[Phase 4] Sprint id=%s 課題取得失敗 code=%s err=%s", sid, fetch_code, fetch_err)
            #     continue
            planned = 0.0
            completed = 0.0
            for issue_data in issues:
                issue = issue_data.raw
                flds = (issue or {}).get("fields", {})
                sp_raw = flds.get(story_points_field)
                sp_val = _normalize_story_points(sp_raw)
                planned += sp_val
                if _is_done(flds.get("status")):
                    completed += sp_val
            if planned == 0 and completed == 0:
                if enable_logging:
                    print("[Phase 4] Sprint id=%s 課題0件 -> サンプル除外 (issues=%d)", sid, len(issues))
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
                print("[Phase 4] Sprint集計完了 id=%s planned=%.2f completed=%.2f rate=%.1f%%", sid, sample["plannedSP"], sample["completedSP"], rate*100)
        if not samples:
            if enable_logging:
                print("[Phase 4] Historical Velocity: 有効サンプル0件 (全closed sprint SP=0?)")
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
            print(
                "[Phase 4] Historical Velocity集計完了 sampleCount=%d averageCompletedSP=%.2f averagePlannedSP=%.2f", result["sampleCount"], result["averageCompletedSP"], result["averagePlannedSP"]
            )
        return result
    except Exception as e:  # pragma: no cover
        print("Historical velocity計算失敗: %s", e)
        return None


def _normalize_status_key(name: str) -> str:
    """ステータス名を比較用に正規化する。"""
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


_DONE_STATUS_KEYS = {
    _normalize_status_key(label)
    for label in ("Done", "Closed", "Resolved", "完了", "完成", "終了")
}


def _parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    """ISO8601文字列をdatetimeに変換する。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """datetimeをUTCに変換する。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_done_status_name(name: Optional[str]) -> bool:
    """ステータス名が完了カテゴリに該当するか判定する。"""
    if not name:
        return False
    normalized = _normalize_status_key(name)
    return normalized in _DONE_STATUS_KEYS


def _calculate_time_in_status(
    metadata: JiraMetadata,
    unit: str = "days",
    scope: str = "sprint",
    enable_logging: bool = True,
) -> Optional[Dict[str, Any]]:
        """各ステータスへの滞留時間を集計する。"""

    # try:
        unit_normalized = (unit or "days").strip().lower()
        if unit_normalized not in {"hours", "days"}:
            unit_normalized = "days"

        scope_normalized = (scope or "sprint").strip().lower()
        utc_now = datetime.now(tz=timezone.utc)

        if enable_logging:
            print(
                "[Phase 4] Time-in-status: target scope=%s unit=%s",
                scope_normalized,
                unit_normalized,
            )

        if scope_normalized == "project":
            project_key = metadata.project_key
            if not project_key:
                if enable_logging:
                    print("[Phase 4] Time-in-status: project scope だが project_key が取得できません")
                return None
            jql = f"project={project_key}"
            calc_since = utc_now - timedelta(days=14)
            calc_until = utc_now
        else:
            sprint_id = metadata.sprint["id"]
            if sprint_id is None:
                if enable_logging:
                    print("[Phase 4] Time-in-status: sprint ID が不明のため計算をスキップします")
                return None
            jql = f"Sprint={sprint_id}"
            print(metadata.sprint)
            calc_since = _to_utc(_parse_iso8601(metadata.sprint["startDate"]))
            calc_until = _to_utc(_parse_iso8601(metadata.sprint["endDate"]))
            if calc_since is None:
                calc_since = utc_now - timedelta(days=14)
            if calc_until is None:
                calc_until = utc_now

        if enable_logging:
            print(
                "[Phase 4] Time-in-status: JQL=%s window=%s -> %s",
                jql,
                calc_since.isoformat(),
                calc_until.isoformat(),
            )

        if calc_until < calc_since:
            calc_until = calc_since

        request_jira = RequestJiraRepository()
        issues = request_jira.request_jql(query=jql,fields=["status"])


        # if code != 200:
        #     if enable_logging:
        #         print(
        #             "[Phase 4] Time-in-status: 課題取得失敗 code=%s err=%s", code, err
        #         )
        #     return None

        # if enable_logging:
        #     print(
        #         "[Phase 4] Time-in-status: 課題取得件数=%s",
        #         len(issues),
        #     )

        total_by_status: Dict[str, float] = {}
        per_issue_results: List[Dict[str, Any]] = []

        for issue in issues:
            issue = issue.raw
            issue_id = issue.get("id") or issue.get("key")
            issue_key = issue.get("key") or str(issue_id)
            if not issue_id:
                per_issue_results.append({"key": issue_key, "byStatus": {}})
                continue
            
            detail_data = request_jira.get_issue(issue_id, expand="changelog")

            if not detail_data:
                # if enable_logging:
                #     print(
                #         "[Phase 4] Time-in-status: 課題詳細取得失敗 key=%s code=%s err=%s",
                #         issue_key,
                #         detail_code,
                #         detail_err,
                #     )
                per_issue_results.append({"key": issue_key, "byStatus": {}})
                continue
            detail_data = detail_data.raw
            fields = detail_data.get("fields", {})
            created = _to_utc(_parse_iso8601(fields.get("created")))
            current_status_name = ((fields.get("status") or {}).get("name") or "").strip() or "(unknown)"

            histories = ((detail_data.get("changelog") or {}).get("histories") or [])
            events: List[tuple[datetime, str]] = []
            for history in histories:
                changed_at = _to_utc(_parse_iso8601(history.get("created")))
                if not changed_at:
                    continue
                for item in history.get("items") or []:
                    field_name = str(item.get("field") or "").lower()
                    if field_name != "status":
                        continue
                    to_status = item.get("toString") or item.get("to")
                    if to_status:
                        events.append((changed_at, str(to_status)))

            events.sort(key=lambda row: row[0])

            current_reference = datetime.now(tz=timezone.utc)

            if not events:
                # ステータス変更履歴が無い場合は現在ステータスに全期間を割り当て
                if _is_done_status_name(current_status_name):
                    per_issue_results.append({"key": issue_key, "byStatus": {}})
                    continue
                effective_start = calc_since
                if created:
                    effective_start = max(calc_since, created)
                effective_end = min(current_reference, calc_until)
                duration = (effective_end - effective_start).total_seconds()
                if duration > 0:
                    total_by_status[current_status_name] = total_by_status.get(current_status_name, 0.0) + duration
                    per_issue_results.append({"key": issue_key, "byStatus": {current_status_name: duration}})
                else:
                    per_issue_results.append({"key": issue_key, "byStatus": {}})
                continue

            by_status: Dict[str, float] = {}
            prev_time = max(calc_since, events[0][0])
            prev_status = events[0][1]

            for event_time, status_name in events[1:]:
                if event_time <= calc_since:
                    prev_time = calc_since
                    prev_status = status_name
                    continue
                if event_time > calc_until:
                    break
                duration = (event_time - prev_time).total_seconds()
                if duration > 0 and prev_status and not _is_done_status_name(prev_status):
                    by_status[prev_status] = by_status.get(prev_status, 0.0) + duration
                prev_time = event_time
                prev_status = status_name

            if prev_status and not _is_done_status_name(prev_status):
                effective_end = min(current_reference, calc_until)
                tail = (effective_end - max(prev_time, calc_since)).total_seconds()
                if tail > 0:
                    by_status[prev_status] = by_status.get(prev_status, 0.0) + tail

            for status_name, seconds in by_status.items():
                total_by_status[status_name] = total_by_status.get(status_name, 0.0) + seconds

            per_issue_results.append({"key": issue_key, "byStatus": by_status})

        if not total_by_status and not per_issue_results:
            if enable_logging:
                print("[Phase 4] Time-in-status: 滞留データが取得できませんでした")
            return None

        denom = 3600.0 if unit_normalized == "hours" else 86400.0
        total_converted = {name: seconds / denom for name, seconds in total_by_status.items()}
        per_issue_converted = [
            {
                "key": row["key"],
                "byStatus": {name: seconds / denom for name, seconds in (row.get("byStatus") or {}).items()},
            }
            for row in per_issue_results
        ]

        sprint_info = None
        project_info = None
        if scope_normalized == "sprint":
            sprint_info = {
                "id": metadata.sprint["id"],
                "name": metadata.sprint["name"],
            }
        else:
            project_info = metadata.project_key

        result = {
            "scope": scope_normalized,
            "sprint": sprint_info,
            "project": project_info,
            "window": {
                "since": calc_since.isoformat(),
                "until": calc_until.isoformat(),
                "unit": unit_normalized,
            },
            "totalByStatus": total_converted,
            "perIssue": per_issue_converted,
        }

        if enable_logging:
            print(
                "[Phase 4] Time-in-status: 課題=%d ステータス=%d",
                len(per_issue_converted),
                len(total_converted),
            )

        return result

    # except Exception as exc:  # pragma: no cover - 予期せぬ失敗時はNoneにフォールバック
    #     if enable_logging:
    #         print("[Phase 4] Time-in-status計算中にエラー: %s", exc)
    #     return None


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
