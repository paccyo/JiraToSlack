"""
Test suite for Dashboard Orchestrator (Phase 1-7 integration)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "prototype" / "local_cli"))

from core.orchestrator import DashboardOrchestrator, run_dashboard_generation, OrchestratorError
from core.phase1_environment import EnvironmentConfig, AuthContext
from core.phase2_metadata import JiraMetadata
from core.phase3_core_data import CoreData
from core.phase4_metrics import MetricsCollection
from core.phase5_summary import AISummary
from core.phase7_output import OutputPaths


@pytest.fixture
def mock_config():
    """モック環境設定"""
    return EnvironmentConfig(
        jira_domain="https://test.atlassian.net",
        jira_email="test@example.com",
        jira_api_token="test-token",
        output_dir="/tmp/test",
        target_done_rate=0.8,
        gemini_api_key="test-key"
    )


@pytest.fixture
def mock_auth_ctx():
    """モック認証コンテキスト"""
    from requests.auth import HTTPBasicAuth
    return AuthContext(
        domain="https://test.atlassian.net",
        auth=HTTPBasicAuth("user@example.com", "test-token")
    )


@pytest.fixture
def mock_jira_metadata():
    """モックJiraメタデータ"""
    from core.types import BoardMetadata, SprintMetadata
    return JiraMetadata(
        board=BoardMetadata(
            board={"id": 123, "name": "Test Board"},
            board_id=123,
            project_key="PROJ",
            boards_count=1
        ),
        sprint=SprintMetadata(
            sprint={"id": 456, "name": "Sprint 10"},
            sprint_id=456,
            sprint_name="Sprint 10",
            sprint_start="2024-01-01",
            sprint_end="2024-01-14",
            active_sprints_count=1
        ),
        project_key="PROJ"
    )


@pytest.fixture
def mock_core_data():
    """モックコアデータ"""
    from core.types import TaskTotals
    return CoreData(
        parents=[],
        totals=TaskTotals(subtasks=10, done=5, not_done=5)
    )


@pytest.fixture
def mock_metrics():
    """モックメトリクス"""
    return MetricsCollection(
        kpis={"completion_rate": 50},
        assignee_workload={}
    )


@pytest.fixture
def mock_ai_summary():
    """モックAI要約"""
    return AISummary(
        full_text="Test summary",
        evidence_reasons={"key1": "Reason 1"}
    )


@pytest.fixture
def mock_output_paths():
    """モック出力パス"""
    return OutputPaths(
        report_md=Path("/tmp/report.md"),
        tasks_json=Path("/tmp/tasks.json"),
        data_json=Path("/tmp/data.json")
    )


class TestDashboardOrchestrator:
    """DashboardOrchestratorクラスのテスト"""
    
    def test_initialization(self):
        """オーケストレーターが正しく初期化される"""
        orchestrator = DashboardOrchestrator(enable_logging=False)
        
        assert orchestrator.enable_logging is False
        assert orchestrator.config is None
        assert orchestrator.auth_ctx is None
        assert orchestrator.jira_metadata is None
        assert orchestrator.core_data is None
        assert orchestrator.metrics is None
        assert orchestrator.ai_summary is None
        assert orchestrator.image_path is None
        assert orchestrator.output_paths is None
    
    @patch('core.orchestrator.setup_environment')
    @patch('core.orchestrator.fetch_jira_metadata')
    @patch('core.orchestrator.fetch_core_data')
    @patch('core.orchestrator.collect_metrics')
    @patch('core.orchestrator.generate_ai_summary')
    @patch('core.orchestrator.render_dashboard')
    @patch('core.orchestrator.generate_all_outputs')
    def test_run_success(
        self,
        mock_output,
        mock_dashboard,
        mock_ai,
        mock_metrics_func,
        mock_core,
        mock_meta,
        mock_env,
        mock_config,
        mock_auth_ctx,
        mock_jira_metadata,
        mock_core_data,
        mock_metrics,
        mock_ai_summary,
        mock_output_paths
    ):
        """全フェーズが正常に実行される"""
        # モック設定
        mock_env.return_value = (mock_config, mock_auth_ctx)
        mock_meta.return_value = mock_jira_metadata
        mock_core.return_value = mock_core_data
        mock_metrics_func.return_value = mock_metrics
        mock_ai.return_value = mock_ai_summary
        test_image_path = Path("/tmp/test.png")
        mock_dashboard.return_value = test_image_path
        mock_output.return_value = mock_output_paths
        
        # 実行
        orchestrator = DashboardOrchestrator(enable_logging=False)
        result = orchestrator.run()
        
        # 検証
        assert result == test_image_path
        assert orchestrator.config == mock_config
        assert orchestrator.auth_ctx == mock_auth_ctx
        assert orchestrator.jira_metadata == mock_jira_metadata
        assert orchestrator.core_data == mock_core_data
        assert orchestrator.metrics == mock_metrics
        assert orchestrator.ai_summary == mock_ai_summary
        assert orchestrator.image_path == test_image_path
        assert orchestrator.output_paths == mock_output_paths
        
        # 全フェーズが呼ばれたことを確認
        mock_env.assert_called_once()
        mock_meta.assert_called_once_with(mock_auth_ctx, enable_logging=False)
        mock_core.assert_called_once_with(mock_auth_ctx, mock_jira_metadata, enable_logging=False)
        mock_metrics_func.assert_called_once_with(
            mock_auth_ctx,
            mock_jira_metadata,
            mock_core_data,
            enable_logging=False
        )
        mock_ai.assert_called_once_with(
            mock_config,
            mock_jira_metadata,
            mock_core_data,
            mock_metrics,
            enable_logging=False
        )
        mock_dashboard.assert_called_once_with(
            mock_config,
            mock_jira_metadata,
            mock_core_data,
            mock_metrics,
            mock_ai_summary,
            enable_logging=False
        )
        mock_output.assert_called_once_with(
            mock_config,
            mock_jira_metadata,
            mock_core_data,
            mock_metrics,
            mock_ai_summary,
            enable_logging=False
        )
    
    @patch('core.orchestrator.setup_environment')
    def test_run_phase1_failure(self, mock_env):
        """Phase 1で失敗した場合OrchestratorErrorが発生"""
        mock_env.side_effect = Exception("Phase 1 failed")
        
        orchestrator = DashboardOrchestrator(enable_logging=False)
        
        with pytest.raises(OrchestratorError, match="Phase 1 failed"):
            orchestrator.run()
    
    @patch('core.orchestrator.setup_environment')
    @patch('core.orchestrator.fetch_jira_metadata')
    def test_run_phase2_failure(
        self,
        mock_meta,
        mock_env,
        mock_config,
        mock_auth_ctx
    ):
        """Phase 2で失敗した場合OrchestratorErrorが発生"""
        mock_env.return_value = (mock_config, mock_auth_ctx)
        mock_meta.side_effect = Exception("Phase 2 failed")
        
        orchestrator = DashboardOrchestrator(enable_logging=False)
        
        with pytest.raises(OrchestratorError, match="Phase 2 failed"):
            orchestrator.run()
    
    @patch('core.orchestrator.setup_environment')
    @patch('core.orchestrator.fetch_jira_metadata')
    @patch('core.orchestrator.fetch_core_data')
    def test_run_phase3_failure(
        self,
        mock_core,
        mock_meta,
        mock_env,
        mock_config,
        mock_auth_ctx,
        mock_jira_metadata
    ):
        """Phase 3で失敗した場合OrchestratorErrorが発生"""
        mock_env.return_value = (mock_config, mock_auth_ctx)
        mock_meta.return_value = mock_jira_metadata
        mock_core.side_effect = Exception("Phase 3 failed")
        
        orchestrator = DashboardOrchestrator(enable_logging=False)
        
        with pytest.raises(OrchestratorError, match="Phase 3 failed"):
            orchestrator.run()
    
    @patch('core.orchestrator.setup_environment')
    @patch('core.orchestrator.fetch_jira_metadata')
    @patch('core.orchestrator.fetch_core_data')
    @patch('core.orchestrator.collect_metrics')
    @patch('core.orchestrator.generate_ai_summary')
    @patch('core.orchestrator.render_dashboard')
    def test_run_phase6_failure(
        self,
        mock_dashboard,
        mock_ai,
        mock_metrics_func,
        mock_core,
        mock_meta,
        mock_env,
        mock_config,
        mock_auth_ctx,
        mock_jira_metadata,
        mock_core_data,
        mock_metrics,
        mock_ai_summary
    ):
        """Phase 6で失敗した場合OrchestratorErrorが発生"""
        mock_env.return_value = (mock_config, mock_auth_ctx)
        mock_meta.return_value = mock_jira_metadata
        mock_core.return_value = mock_core_data
        mock_metrics_func.return_value = mock_metrics
        mock_ai.return_value = mock_ai_summary
        mock_dashboard.side_effect = Exception("Phase 6 failed")
        
        orchestrator = DashboardOrchestrator(enable_logging=False)
        
        with pytest.raises(OrchestratorError, match="Phase 6 failed"):
            orchestrator.run()


class TestRunDashboardGeneration:
    """run_dashboard_generation関数のテスト"""
    
    @patch('core.orchestrator.DashboardOrchestrator')
    def test_success(self, mock_orchestrator_class, capsys):
        """正常実行時は0を返し画像パスを出力"""
        test_image_path = Path("/tmp/test_dashboard.png")
        mock_instance = Mock()
        mock_instance.run.return_value = test_image_path
        mock_orchestrator_class.return_value = mock_instance
        
        result = run_dashboard_generation(enable_logging=False)
        
        assert result == 0
        mock_orchestrator_class.assert_called_once_with(enable_logging=False)
        mock_instance.run.assert_called_once()
        
        captured = capsys.readouterr()
        assert str(test_image_path) in captured.out
    
    @patch('core.orchestrator.DashboardOrchestrator')
    def test_orchestrator_error(self, mock_orchestrator_class):
        """OrchestratorError発生時は1を返す"""
        mock_instance = Mock()
        mock_instance.run.side_effect = OrchestratorError("Test error")
        mock_orchestrator_class.return_value = mock_instance
        
        result = run_dashboard_generation(enable_logging=False)
        
        assert result == 1
    
    @patch('core.orchestrator.DashboardOrchestrator')
    def test_unexpected_error(self, mock_orchestrator_class):
        """予期しない例外発生時は1を返す"""
        mock_instance = Mock()
        mock_instance.run.side_effect = RuntimeError("Unexpected error")
        mock_orchestrator_class.return_value = mock_instance
        
        result = run_dashboard_generation(enable_logging=False)
        
        assert result == 1
