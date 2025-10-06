"""
Phase 6: ダッシュボード描画
Pdef render_dashboard(
    config: EnvironmentConfig,
    metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    ai_summary: Optional[AISummary] = None,
    enable_logging: bool = False,
    _draw_png_func=None,  # テスト用のインジェクションポイント
) -> Path:してダッシュボードPNG画像を生成する。
"""

import importlib.util
import logging
from pathlib import Path
from typing import Optional

from .types import (
    EnvironmentConfig,
    JiraMetadata,
    CoreData,
    MetricsCollection,
    AISummary,
)

logger = logging.getLogger(__name__)


class DashboardError(Exception):
    """ダッシュボード描画時のエラー"""
    pass


def render_dashboard(
    config: EnvironmentConfig,
    metadata: JiraMetadata,
    core_data: CoreData,
    metrics: MetricsCollection,
    ai_summary: Optional[AISummary] = None,
    enable_logging: bool = False,
    _draw_png_func=None  # テスト用のインジェクションポイント
) -> Path:
    """
    Phase 6: ダッシュボードPNG画像を生成する。
    
    Args:
        config: 環境設定
        metadata: Jiraメタデータ
        core_data: コアデータ
        metrics: メトリクス
        ai_summary: AI要約（任意）
        enable_logging: ログ出力を有効化するかどうか
        _draw_png_func: テスト用の描画関数（通常はNone）
    
    Returns:
        Path: 生成した画像ファイルのパス
    
    Raises:
        DashboardError: 描画に失敗した場合
    """
    if enable_logging:
        logger.info("[Phase 6] ダッシュボード描画を開始します")
    
    try:
        # 出力パスを構築
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / "sprint_overview.png"
        
        # メトリクスをextras辞書形式に変換
        extras = metrics.to_dict()
        
        # AI要約を統合（後方互換性のため）
        if ai_summary and ai_summary.full_text:
            extras["ai_full_text"] = ai_summary.full_text
        
        if ai_summary and ai_summary.evidence_reasons:
            extras["ai_reasons"] = ai_summary.evidence_reasons
        
        # 既存のdraw_png関数を呼び出し
        # main.pyから直接インポート
        if _draw_png_func is None:
            # 通常の実行: main.pyから動的にインポート
            try:
                # main.pyのパスを取得
                main_path = Path(__file__).parent.parent / "main.py"
                
                if not main_path.exists():
                    raise DashboardError(f"main.py が見つかりません: {main_path}")
                
                # main.pyを動的にインポート
                spec = importlib.util.spec_from_file_location("main_module", main_path)
                if spec is None or spec.loader is None:
                    raise DashboardError("main.py のインポートに失敗しました")
                
                main_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(main_module)
                
                draw_png = main_module.draw_png
                
            except Exception as e:
                raise DashboardError(f"draw_png関数のインポートに失敗: {e}") from e
        else:
            # テスト時: インジェクトされた関数を使用
            draw_png = _draw_png_func
        
        if enable_logging:
            logger.info(f"[Phase 6] 画像を生成中: {output_path}")
        
        # draw_pngを呼び出し
        try:
            draw_png(
                output_path=str(output_path),
                data=core_data.to_dict(),
                boards_n=metadata.board.boards_count,
                sprints_n=metadata.sprint.active_sprints_count,
                sprint_name=metadata.sprint.sprint_name,
                sprint_start=metadata.sprint.sprint_start,
                sprint_end=metadata.sprint.sprint_end,
                axis_mode=config.axis_mode,
                target_done_rate=config.target_done_rate,
                extras=extras,
            )
        except Exception as e:
            raise DashboardError(f"ダッシュボード描画エラー: {e}") from e
        
        if enable_logging:
            logger.info(f"[Phase 6] ダッシュボード描画が完了しました: {output_path}")
        
        return output_path
        
    except DashboardError:
        raise
    except Exception as e:
        raise DashboardError(f"予期しないエラー: {e}") from e
