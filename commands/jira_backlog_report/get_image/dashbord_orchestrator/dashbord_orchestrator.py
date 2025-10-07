import logging
import os
from pathlib import Path
from typing import Optional


from commands.jira_backlog_report.get_image.dashbord_orchestrator.phase1_environment import setup_environment, EnvironmentConfig, AuthContext
from commands.jira_backlog_report.get_image.dashbord_orchestrator.phase2_metadata import get_jira_artifacts, JiraMetadata
from commands.jira_backlog_report.get_image.dashbord_orchestrator.phase3_core_data import fetch_core_data, CoreData
from commands.jira_backlog_report.get_image.dashbord_orchestrator.phase4_metrics import collect_metrics, MetricsCollection
from commands.jira_backlog_report.get_image.dashbord_orchestrator.phase5_summary import generate_ai_summary, AISummary
from commands.jira_backlog_report.get_image.dashbord_orchestrator.phase6_dashboard import render_dashboard
from commands.jira_backlog_report.get_image.dashbord_orchestrator.phase7_output import generate_all_outputs, OutputPaths

class DashboardOrchestrator:
    """ダッシュボード生成を統括するオーケストレーター"""
    
    def __init__(self, enable_logging: bool = True):
        """
        Args:
            enable_logging: ログ出力を有効化するかどうか
        """
        self.enable_logging = enable_logging
    
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
                print("🚀 Dashboard generation started")
            
            # Phase 1: 環境準備
            # if self.enable_logging:
            #     print("[Phase 1] Environment setup")
            # self.config, self.auth_ctx = setup_environment()
            
            # Phase 2: メタデータ取得
            if self.enable_logging:
                print("[Phase 2] Fetching Jira metadata")
            jira_metadata = get_jira_artifacts()
            
            # Phase 3: コアデータ取得
            if self.enable_logging:
                print("[Phase 3] Fetching core data")
            core_data = fetch_core_data(
                jira_metadata,
            )
            
            # Phase 4: メトリクス収集
            if self.enable_logging:
                print("[Phase 4] Collecting metrics")
            metrics = collect_metrics(
                self.jira_metadata,
                self.core_data,
            )
            
            # Phase 5: AI要約生成
            if self.enable_logging:
                print("[Phase 5] Generating AI summary")
            ai_summary = generate_ai_summary(
                self.jira_metadata,
                self.core_data,
                self.metrics,
                enable_logging=self.enable_logging
            )
            
            # Phase 6: 画像描画
            if self.enable_logging:
                print("[Phase 6] Rendering dashboard")
            image_bytes = render_dashboard(
                jira_metadata,
                core_data,
                metrics,
                ai_summary,
                enable_logging=self.enable_logging
            )
            
            # Phase 7: 追加出力
            # if self.enable_logging:
            #     print("[Phase 7] Generating additional outputs")
            # self.output_paths = generate_all_outputs(
            #     self.config,
            #     self.jira_metadata,
            #     self.core_data,
            #     self.metrics,
            #     self.ai_summary,
            #     enable_logging=self.enable_logging
            # )
            
            # if self.enable_logging:
            #     print(f"✅ Dashboard generation completed: {self.image_path}")
            #     print(f"   Report: {self.output_paths.report_md}")
            #     print(f"   Tasks: {self.output_paths.tasks_json}")
            #     print(f"   Metrics: {self.output_paths.data_json}")
            
            return image_bytes
        
        except Exception as e:
            error_msg = f"Dashboard generation failed: {e}"
            print(f"❌ {error_msg}", exc_info=True)
