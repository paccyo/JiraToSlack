"""
Dashboard Generation Orchestrator
Phase 1-7を統合してダッシュボード生成を実行
"""

import logging
from pathlib import Path
from typing import Optional

from .phase1_environment import setup_environment, EnvironmentConfig, AuthContext
from .phase2_metadata import fetch_jira_metadata, JiraMetadata
from .phase3_core_data import fetch_core_data, CoreData
from .phase4_metrics import collect_metrics, MetricsCollection
from .phase5_summary import generate_ai_summary, AISummary
from .phase6_dashboard import render_dashboard
from .phase7_output import generate_all_outputs, OutputPaths

logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """オーケストレーター実行時のエラー"""
    pass


class DashboardOrchestrator:
    """ダッシュボード生成を統括するオーケストレーター"""
    
    def __init__(self, enable_logging: bool = True):
        """
        Args:
            enable_logging: ログ出力を有効化するかどうか
        """
        self.enable_logging = enable_logging
        self.config: Optional[EnvironmentConfig] = None
        self.auth_ctx: Optional[AuthContext] = None
        self.jira_metadata: Optional[JiraMetadata] = None
        self.core_data: Optional[CoreData] = None
        self.metrics: Optional[MetricsCollection] = None
        self.ai_summary: Optional[AISummary] = None
        self.image_path: Optional[Path] = None
        self.output_paths: Optional[OutputPaths] = None
    
    def run(self) -> Path:
        """
        全フェーズを実行してダッシュボードを生成
        
        Returns:
            Path: 生成した画像ファイルのパス
        
        Raises:
            OrchestratorError: いずれかのフェーズで失敗した場合
        """
        try:
            if self.enable_logging:
                logger.info("🚀 Dashboard generation started")
            
            # Phase 1: 環境準備
            if self.enable_logging:
                logger.info("📋 Phase 1: Environment setup")
            self.config, self.auth_ctx = setup_environment()
            
            # Phase 2: メタデータ取得
            if self.enable_logging:
                logger.info("🔍 Phase 2: Fetching Jira metadata")
            self.jira_metadata = fetch_jira_metadata(
                self.auth_ctx,
                enable_logging=self.enable_logging
            )
            
            # Phase 3: コアデータ取得
            if self.enable_logging:
                logger.info("📊 Phase 3: Fetching core data")
            self.core_data = fetch_core_data(
                self.auth_ctx,
                self.jira_metadata,
                enable_logging=self.enable_logging
            )
            
            # Phase 4: メトリクス収集
            if self.enable_logging:
                logger.info("📈 Phase 4: Collecting metrics")
            self.metrics = collect_metrics(
                self.auth_ctx,
                self.jira_metadata,
                self.core_data,
                enable_logging=self.enable_logging
            )
            
            # Phase 5: AI要約生成
            if self.enable_logging:
                logger.info("🤖 Phase 5: Generating AI summary")
            self.ai_summary = generate_ai_summary(
                self.config,
                self.jira_metadata,
                self.core_data,
                self.metrics,
                enable_logging=self.enable_logging
            )
            
            # Phase 6: 画像描画
            if self.enable_logging:
                logger.info("🎨 Phase 6: Rendering dashboard")
            self.image_path = render_dashboard(
                self.config,
                self.jira_metadata,
                self.core_data,
                self.metrics,
                self.ai_summary,
                enable_logging=self.enable_logging
            )
            
            # Phase 7: 追加出力
            if self.enable_logging:
                logger.info("📄 Phase 7: Generating additional outputs")
            self.output_paths = generate_all_outputs(
                self.config,
                self.jira_metadata,
                self.core_data,
                self.metrics,
                self.ai_summary,
                enable_logging=self.enable_logging
            )
            
            if self.enable_logging:
                logger.info(f"✅ Dashboard generation completed: {self.image_path}")
                logger.info(f"   Report: {self.output_paths.report_md}")
                logger.info(f"   Tasks: {self.output_paths.tasks_json}")
                logger.info(f"   Metrics: {self.output_paths.data_json}")
            
            return self.image_path
        
        except Exception as e:
            error_msg = f"Dashboard generation failed: {e}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            raise OrchestratorError(error_msg) from e


def run_dashboard_generation(enable_logging: bool = True) -> int:
    """
    ダッシュボード生成を実行（エラーハンドリング付き）
    
    Args:
        enable_logging: ログ出力を有効化するかどうか
    
    Returns:
        int: 終了コード（0=成功、1=失敗）
    """
    try:
        orchestrator = DashboardOrchestrator(enable_logging=enable_logging)
        image_path = orchestrator.run()
        
        # 画像パスを出力（既存のmain.pyとの互換性）
        print(str(image_path))
        
        return 0
    
    except OrchestratorError as e:
        if enable_logging:
            logger.error(f"❌ Dashboard generation failed: {e}")
        return 1
    
    except Exception as e:
        if enable_logging:
            logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        return 1
