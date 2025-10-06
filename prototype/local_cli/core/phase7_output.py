"""
Phase 7: ファイル出力
Markdown、JSON形式での各種レポート生成
"""

import logging
import json
from pathlib import Path
from typing import Optional
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
        
        # エビデンス
        if evidence:
            md.append("")
            md.append("## エビデンス (Top)")
            for e in evidence[:5]:  # Top 5
                key = e.get('key', '')
                summary = e.get('summary', '').strip()
                status = e.get('status', '')
                days = e.get('days', 0)
                assignee = e.get('assignee', '')
                why = e.get('why', '')
                link = e.get('link', '')
                
                label = f"{key} {summary}" if summary else key
                md.append(f"- {label} | {status} | {days:.1f}d | assignee: {assignee} | why: {why} | {link}")
        
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
