"""
Phase 7: ファイル出力
Markdown、JSON形式での各種レポート生成
"""

import logging
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime

from .types import (
    EnvironmentConfig,
    JiraMetadata,
    CoreData,
    MetricsCollection,
    AISummary,
)

logger = logging.getLogger(__name__)


class OutputError(Exception):
    """ファイル出力時のエラー"""
    pass


class OutputPaths:
    """出力ファイルパス"""
    def __init__(self, report_md: Path, tasks_json: Path, data_json: Path):
        self.report_md = report_md
        self.tasks_json = tasks_json
        self.data_json = data_json


def generate_markdown_report(
    output_path: Path,
    metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    ai_summary: Optional[AISummary],
    target_done_rate: float,
    enable_logging: bool = False
) -> None:
    """
    Markdownレポートを生成
    
    Args:
        output_path: 出力先パス
        metadata: Jiraメタデータ
        core_data: コアデータ
        metrics: メトリクス
        ai_summary: AI要約（任意）
        target_done_rate: 目標達成率
        enable_logging: ログ出力を有効化するかどうか
    
    Raises:
        OutputError: ファイル書き込みに失敗した場合
    """
    if enable_logging:
        logger.info(f"[Phase 7] Markdownレポートを生成中: {output_path}")
    
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 基本情報
        sprint_label = f"{metadata.sprint.sprint_name} ({metadata.sprint.sprint_start} ~ {metadata.sprint.sprint_end})"
        sprint_total = core_data.totals.subtasks
        sprint_done = core_data.totals.done
        completion_rate = core_data.totals.completion_rate
        
        # メトリクス情報
        kpis = metrics.kpis
        risks = metrics.risks
        evidence = metrics.evidence or []
        time_in_status = metrics.time_in_status
        
        # Markdown構築
        md = []
        md.append(f"## 要約 | {ts}")
        md.append(f"What: {sprint_label} — {sprint_total} tasks, Done {sprint_done} ({int(completion_rate*100)}%)")
        
        # 進捗評価
        if completion_rate < target_done_rate:
            md.append(f"So what: 目標{int(target_done_rate*100)}%未達")
        else:
            md.append("So what: 目標達成ペース")
        
        # AI要約を追加
        if ai_summary and ai_summary.full_text:
            md.append("")
            md.append("## AI要約 (Gemini)")
            md.append("")
            md.append(ai_summary.full_text.strip())
            md.append("")
        
        # リスク情報
        md.append("## リスク")
        has_risk = False
        
        if risks.get("overdue", 0) > 0:
            md.append(f"- 期限超過: {risks['overdue']}件 — 優先割当要")
            has_risk = True
        
        if risks.get("due_soon", 0) > 0:
            md.append(f"- 7日以内期限: {risks['due_soon']}件")
            has_risk = True
        
        if risks.get("high_priority_todo", 0) > 0:
            md.append(f"- 高優先度未着手: {risks['high_priority_todo']}件")
            has_risk = True
        
        if not has_risk:
            md.append("- 特筆すべきリスクなし")

        # サイクルタイム / 滞留時間
        tis_total: Dict[str, float] = {}
        tis_window_unit = "days"
        tis_issues: List[Dict[str, Any]] = []
        if isinstance(time_in_status, dict):
            tis_total = {k: float(v) for k, v in (time_in_status.get("totalByStatus") or {}).items() if isinstance(v, (int, float))}
            tis_window = time_in_status.get("window") or {}
            tis_window_unit = str(tis_window.get("unit") or "days").lower()
            tis_issues = time_in_status.get("perIssue") or []

        if tis_total:
            md.append("")
            md.append("## サイクルタイム (滞留時間)")
            window_info = (time_in_status or {}).get("window") if isinstance(time_in_status, dict) else None
            window_since = (window_info or {}).get("since") if isinstance(window_info, dict) else None
            window_until = (window_info or {}).get("until") if isinstance(window_info, dict) else None
            unit_label = "時間" if tis_window_unit.startswith("hour") else "日"
            if window_since or window_until:
                md.append(f"*対象期間: {window_since or '?'} 〜 {window_until or '?'}*")

            top_statuses = sorted(tis_total.items(), key=lambda item: item[1], reverse=True)
            shown = 0
            for status_name, duration in top_statuses:
                if duration <= 0:
                    continue
                md.append(f"- {status_name}: {duration:.1f}{unit_label}")
                shown += 1
                if shown >= 5:
                    break

            issue_totals: List[Tuple[str, float]] = []
            for row in tis_issues:
                if not isinstance(row, dict):
                    continue
                key = str(row.get("key") or "(unknown)")
                durations = row.get("byStatus") or {}
                if not isinstance(durations, dict):
                    continue
                total_duration = sum(float(v) for v in durations.values() if isinstance(v, (int, float)))
                if total_duration > 0:
                    issue_totals.append((key, total_duration))

            if issue_totals:
                issue_totals.sort(key=lambda item: item[1], reverse=True)
                md.append("")
                md.append("### 滞留時間が長い課題 (Top3)")
                for key, total_duration in issue_totals[:3]:
                    md.append(f"- {key}: {total_duration:.1f}{unit_label}")
        
        # エビデンス
        if evidence:
            md.append("")
            md.append("## エビデンス (Top)")

            evidence_reasons = {}
            if ai_summary and ai_summary.evidence_reasons:
                evidence_reasons = {
                    str(k): v.strip()
                    for k, v in ai_summary.evidence_reasons.items()
                    if isinstance(k, str) and isinstance(v, str) and v.strip()
                }

            def _format_days(raw: object) -> str:
                if isinstance(raw, (int, float)):
                    if raw <= 0:
                        return "0日"
                    return f"{raw:.1f}日"
                return "-"

            def _format_due(raw: object) -> Optional[str]:
                if not raw:
                    return None
                if isinstance(raw, str):
                    return raw.strip() or None
                return str(raw)

            top_limit = min(len(evidence), 5)
            for e in evidence[:top_limit]:  # Top evidence entries
                key = str(e.get('key', '') or '').strip()
                summary = (e.get('summary') or '').strip()
                status = (e.get('status') or '').strip() or "未設定"
                assignee = (e.get('assignee') or '').strip() or "(未割り当て)"
                priority = (e.get('priority') or '').strip()
                raw_days = e.get('days')
                due_raw = e.get('duedate') or e.get('due')
                due = _format_due(due_raw)
                days = _format_days(raw_days)
                reason = evidence_reasons.get(key) or (e.get('why') or e.get('reason') or '').strip()
                if not reason:
                    hints = []
                    if priority:
                        hints.append(f"優先度{priority}")
                    if isinstance(raw_days, (int, float)) and raw_days > 0:
                        hints.append(f"滞留{raw_days:.0f}日")
                    if due:
                        hints.append(f"期限 {due}")
                    if not hints:
                        reason = "進捗未入力のため状況確認が必要です"
                    else:
                        reason = " / ".join(hints) + " のため優先対応が必要です"

                label = f"{key} {summary}".strip() if summary else key or summary or "(No Key)"

                detail_parts = [f"状態: {status}", f"担当: {assignee}", f"滞留: {days}"]
                if priority:
                    detail_parts.append(f"優先度: {priority}")
                if due:
                    detail_parts.append(f"期限: {due}")

                md.append(f"- **{label}**")
                md.append(f"  - {' / '.join(detail_parts)}")
                md.append(f"  - 理由: {reason}")
        
        # 短期アクション
        md.append("")
        md.append("## 短期アクション")
        if completion_rate < target_done_rate:
            md.append("1) 期限超過の優先割当とエスカレーション")
            md.append("2) レビュー担当を1名追加 — 期待: Review平均を2日短縮")
        else:
            md.append("1) 現在のペースを維持")
            md.append("2) 完了タスクのレビューを優先")
        
        # ファイル書き込み
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        
        if enable_logging:
            logger.info(f"[Phase 7] Markdownレポートを生成しました: {output_path}")
    
    except Exception as e:
        raise OutputError(f"Markdownレポート生成エラー: {e}") from e


def export_tasks_json(
    output_path: Path,
    metadata: JiraMetadata,
    core_data: CoreData,
    enable_logging: bool = False
) -> None:
    """
    タスクJSONをエクスポート
    
    Args:
        output_path: 出力先パス
        metadata: Jiraメタデータ
        core_data: コアデータ
        enable_logging: ログ出力を有効化するかどうか
    
    Raises:
        OutputError: ファイル書き込みに失敗した場合
    """
    if enable_logging:
        logger.info(f"[Phase 7] タスクJSONをエクスポート中: {output_path}")
    
    try:
        enriched = {
            "sprint": {
                "name": metadata.sprint.sprint_name,
                "startDate": metadata.sprint.sprint_start,
                "endDate": metadata.sprint.sprint_end,
            },
            "parents": [p.to_dict() for p in core_data.parents],
            "totals": core_data.totals.to_dict(),
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(enriched, f, ensure_ascii=False, indent=2)
        
        if enable_logging:
            logger.info(f"[Phase 7] タスクJSONをエクスポートしました: {output_path}")
    
    except Exception as e:
        raise OutputError(f"タスクJSONエクスポートエラー: {e}") from e


def export_metrics_json(
    output_path: Path,
    metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    config: EnvironmentConfig,
    enable_logging: bool = False
) -> None:
    """
    メトリクスJSONをエクスポート（Slack連携用）
    
    Args:
        output_path: 出力先パス
        metadata: Jiraメタデータ
        core_data: コアデータ
        metrics: メトリクス
        config: 環境設定
        enable_logging: ログ出力を有効化するかどうか
    
    Raises:
        OutputError: ファイル書き込みに失敗した場合
    """
    if enable_logging:
        logger.info(f"[Phase 7] メトリクスJSONをエクスポート中: {output_path}")
    
    try:
        metrics_data = {
            "sprint": {
                "name": metadata.sprint.sprint_name,
                "startDate": metadata.sprint.sprint_start,
                "endDate": metadata.sprint.sprint_end,
            },
            "totals": core_data.totals.to_dict(),
            "doneRate": core_data.totals.completion_rate,
            "targetDoneRate": config.target_done_rate,
            "axis": config.axis_mode,
            "velocity": metrics.velocity,
            "timeInStatus": metrics.time_in_status,
            "evidence": metrics.evidence,
            "assigneeWorkload": metrics.assignee_workload,
            "extrasAvailable": {
                "velocity": metrics.velocity is not None,
                "status_counts": metrics.status_counts is not None,
                "time_in_status": metrics.time_in_status is not None,
                "workload": metrics.workload is not None,
                "evidence": metrics.evidence is not None,
            }
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(metrics_data, f, ensure_ascii=False, indent=2)
        
        if enable_logging:
            logger.info(f"メトリクスJSONをエクスポートしました: {output_path}")
    
    except Exception as e:
        raise OutputError(f"メトリクスJSONエクスポートエラー: {e}") from e


def generate_all_outputs(
    config: EnvironmentConfig,
    metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    ai_summary: Optional[AISummary] = None,
    enable_logging: bool = False
) -> OutputPaths:
    """
    Phase 7: すべての追加出力ファイルを生成
    
    Args:
        config: 環境設定
        metadata: Jiraメタデータ
        core_data: コアデータ
        metrics: メトリクス
        ai_summary: AI要約（任意）
        enable_logging: ログ出力を有効化するかどうか
        
    Returns:
        OutputPaths: 生成したファイルのパス
    
    Raises:
        OutputError: ファイル生成に失敗した場合
    """
    if enable_logging:
        logger.info("Phase 7: ファイル出力を開始します")
    
    try:
        base_dir = Path(config.output_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        
        # 各ファイルパスを定義
        report_md = base_dir / "sprint_overview_report.md"
        tasks_json = base_dir / "sprint_overview_tasks.json"
        data_json = base_dir / "sprint_overview_data.json"
        
        # Markdownレポート生成
        generate_markdown_report(
            report_md,
            metadata,
            core_data,
            metrics,
            ai_summary,
            config.target_done_rate,
            enable_logging
        )
        
        # タスクJSON生成
        export_tasks_json(
            tasks_json,
            metadata,
            core_data,
            enable_logging
        )
        
        # メトリクスJSON生成
        export_metrics_json(
            data_json,
            metadata,
            core_data,
            metrics,
            config,
            enable_logging
        )
        
        if enable_logging:
            logger.info("Phase 7: ファイル出力が完了しました")
        
        return OutputPaths(report_md, tasks_json, data_json)
    
    except OutputError:
        raise
    except Exception as e:
        raise OutputError(f"ファイル出力エラー: {e}") from e
