"""
Phase 2のユニットテスト: Jiraメタデータ取得
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from requests.auth import HTTPBasicAuth

import sys
from pathlib import Path
# プロジェクトルートをパスに追加
repo_root = Path(__file__).resolve().parents[2]
prototype_path = repo_root / "prototype" / "local_cli"
if str(prototype_path) not in sys.path:
    sys.path.insert(0, str(prototype_path))

from prototype.local_cli.core.phase2_metadata import (
    fetch_jira_metadata,
    MetadataError,
    _extract_board_metadata,
    _extract_sprint_metadata,
    _infer_project_key_from_board,
)
from prototype.local_cli.core.types import AuthContext, BoardMetadata, SprintMetadata


class TestExtractBoardMetadata:
    """BoardMetadata抽出のテスト"""
    
    def test_extract_board_metadata_success(self):
        """正常なボードデータからメタデータを抽出"""
        board_data = {
            "id": 123,
            "name": "Test Board",
            "type": "scrum",
            "location": {
                "projectKey": "TEST",
                "type": "project"
            }
        }
        
        result = _extract_board_metadata(board_data)
        
        assert result.board_id == 123
        assert result.board == board_data
        assert result.project_key == "TEST"
        assert result.boards_count == 1
    
    def test_extract_board_metadata_missing_id(self):
        """ボードIDがない場合はエラー"""
        board_data = {"name": "Test Board"}
        
        with pytest.raises(MetadataError, match="ボードIDが取得できませんでした"):
            _extract_board_metadata(board_data)
    
    def test_extract_board_metadata_invalid_id(self):
        """ボードIDが不正な場合はエラー"""
        board_data = {"id": "invalid"}
        
        with pytest.raises(MetadataError, match="ボードIDが不正です"):
            _extract_board_metadata(board_data)
    
    def test_extract_board_metadata_minimal(self):
        """最小限のデータでも動作する"""
        board_data = {"id": 456}
        
        result = _extract_board_metadata(board_data)
        
        assert result.board_id == 456
        assert result.board == board_data
        assert result.project_key is None
        assert result.boards_count == 1


class TestExtractSprintMetadata:
    """SprintMetadata抽出のテスト"""
    
    def test_extract_sprint_metadata_success(self):
        """正常なスプリントデータからメタデータを抽出"""
        sprint_data = {
            "id": 789,
            "name": "Sprint 10",
            "state": "active",
            "startDate": "2025-01-01T00:00:00.000Z",
            "endDate": "2025-01-14T23:59:59.000Z"
        }
        
        result = _extract_sprint_metadata(sprint_data)
        
        assert result.sprint_id == 789
        assert result.sprint_name == "Sprint 10"
        assert result.sprint == sprint_data
        assert result.sprint_start == "2025-01-01T00:00:00.000Z"
        assert result.sprint_end == "2025-01-14T23:59:59.000Z"
        assert result.active_sprints_count == 1
    
    def test_extract_sprint_metadata_missing_id(self):
        """スプリントIDがない場合はエラー"""
        sprint_data = {"name": "Sprint 10"}
        
        with pytest.raises(MetadataError, match="スプリントIDが取得できませんでした"):
            _extract_sprint_metadata(sprint_data)
    
    def test_extract_sprint_metadata_invalid_id(self):
        """スプリントIDが不正な場合はエラー"""
        sprint_data = {"id": "not_a_number"}
        
        with pytest.raises(MetadataError, match="スプリントIDが不正です"):
            _extract_sprint_metadata(sprint_data)
    
    def test_extract_sprint_metadata_minimal(self):
        """最小限のデータでも動作する"""
        sprint_data = {"id": 999}
        
        result = _extract_sprint_metadata(sprint_data)
        
        assert result.sprint_id == 999
        assert result.sprint_name == ""
        assert result.sprint == sprint_data
        assert result.active_sprints_count == 1


class TestInferProjectKey:
    """プロジェクトキー推論のテスト"""
    
    def test_infer_project_key_from_location(self):
        """locationにprojectKeyがある場合"""
        board_data = {
            "location": {
                "projectKey": "MYPROJ"
            }
        }
        
        result = _infer_project_key_from_board(board_data)
        assert result == "MYPROJ"
    
    def test_infer_project_key_no_location(self):
        """locationがない場合"""
        board_data = {}
        
        result = _infer_project_key_from_board(board_data)
        assert result is None
    
    def test_infer_project_key_no_project_key(self):
        """projectKeyがない場合"""
        board_data = {
            "location": {
                "name": "My Project"
            }
        }
        
        result = _infer_project_key_from_board(board_data)
        assert result is None


class TestFetchJiraMetadata:
    """fetch_jira_metadata統合テスト"""
    
    @patch('prototype.local_cli.core.phase2_metadata.JiraClient')
    def test_fetch_jira_metadata_success(self, mock_jira_client_class):
        """正常なメタデータ取得"""
        # JiraClientのモック
        mock_client = MagicMock()
        mock_jira_client_class.return_value = mock_client
        
        # resolve_board のモック
        mock_client.resolve_board.return_value = (
            200,
            {
                "id": 123,
                "name": "Test Board",
                "type": "scrum",
                "location": {"projectKey": "TEST"}
            },
            ""
        )
        
        # resolve_active_sprint のモック
        mock_client.resolve_active_sprint.return_value = (
            200,
            {
                "id": 789,
                "name": "Sprint 10",
                "state": "active"
            },
            ""
        )
        
        # resolve_project_key のモック
        mock_client.resolve_project_key.return_value = "TEST"
        
        # resolve_story_points_field のモック
        mock_client.resolve_story_points_field.return_value = "customfield_10016"
        
        # 実行
        auth = AuthContext(
            domain="https://test.atlassian.net",
            auth=HTTPBasicAuth("test@example.com", "test_token")
        )
        
        result = fetch_jira_metadata(auth, enable_logging=False)
        
        # 検証
        assert result.board.board_id == 123
        assert result.board.board["name"] == "Test Board"
        assert result.sprint.sprint_id == 789
        assert result.sprint.sprint_name == "Sprint 10"
        assert result.project_key == "TEST"
        assert result.story_points_field == "customfield_10016"
    
    @patch('prototype.local_cli.core.phase2_metadata.JiraClient')
    def test_fetch_jira_metadata_board_resolution_failure(self, mock_jira_client_class):
        """ボード解決失敗時のエラー"""
        mock_client = MagicMock()
        mock_jira_client_class.return_value = mock_client
        
        # ボード解決を失敗させる
        mock_client.resolve_board.return_value = (404, None, "Board not found")
        
        auth = AuthContext(
            domain="https://test.atlassian.net",
            auth=HTTPBasicAuth("test@example.com", "test_token")
        )
        
        with pytest.raises(MetadataError, match="ボード解決に失敗しました"):
            fetch_jira_metadata(auth)
    
    @patch('prototype.local_cli.core.phase2_metadata.JiraClient')
    def test_fetch_jira_metadata_sprint_resolution_failure(self, mock_jira_client_class):
        """スプリント解決失敗時のエラー"""
        mock_client = MagicMock()
        mock_jira_client_class.return_value = mock_client
        
        # ボード解決は成功
        mock_client.resolve_board.return_value = (
            200,
            {"id": 123, "name": "Test Board", "type": "scrum"},
            ""
        )
        
        # スプリント解決を失敗させる
        mock_client.resolve_active_sprint.return_value = (404, None, "No active sprint")
        
        auth = AuthContext(
            domain="https://test.atlassian.net",
            auth=HTTPBasicAuth("test@example.com", "test_token")
        )
        
        with pytest.raises(MetadataError, match="アクティブスプリント解決に失敗しました"):
            fetch_jira_metadata(auth)
    
    @patch('prototype.local_cli.core.phase2_metadata.JiraClient')
    def test_fetch_jira_metadata_project_key_fallback(self, mock_jira_client_class):
        """プロジェクトキーがない場合、ボードから推論"""
        mock_client = MagicMock()
        mock_jira_client_class.return_value = mock_client
        
        # ボード解決
        mock_client.resolve_board.return_value = (
            200,
            {
                "id": 123,
                "name": "Test Board",
                "type": "scrum",
                "location": {"projectKey": "FALLBACK"}
            },
            ""
        )
        
        # スプリント解決
        mock_client.resolve_active_sprint.return_value = (
            200,
            {"id": 789, "name": "Sprint 10", "state": "active"},
            ""
        )
        
        # プロジェクトキー解決を失敗させる
        mock_client.resolve_project_key.return_value = None
        
        # ストーリーポイントフィールド
        mock_client.resolve_story_points_field.return_value = "customfield_10016"
        
        auth = AuthContext(
            domain="https://test.atlassian.net",
            auth=HTTPBasicAuth("test@example.com", "test_token")
        )
        
        result = fetch_jira_metadata(auth)
        
        # フォールバックでボードのlocationから取得
        assert result.project_key == "FALLBACK"
    
    @patch('prototype.local_cli.core.phase2_metadata.JiraClient')
    def test_fetch_jira_metadata_project_key_resolution_failure(self, mock_jira_client_class):
        """プロジェクトキーが完全に解決できない場合のエラー"""
        mock_client = MagicMock()
        mock_jira_client_class.return_value = mock_client
        
        # ボード解決（projectKeyなし）
        mock_client.resolve_board.return_value = (
            200,
            {"id": 123, "name": "Test Board", "type": "scrum", "location": {}},
            ""
        )
        
        # スプリント解決
        mock_client.resolve_active_sprint.return_value = (
            200,
            {"id": 789, "name": "Sprint 10", "state": "active"},
            ""
        )
        
        # プロジェクトキー解決を失敗させる
        mock_client.resolve_project_key.return_value = None
        
        auth = AuthContext(
            domain="https://test.atlassian.net",
            auth=HTTPBasicAuth("test@example.com", "test_token")
        )
        
        with pytest.raises(MetadataError, match="プロジェクトキーの解決に失敗しました"):
            fetch_jira_metadata(auth)
