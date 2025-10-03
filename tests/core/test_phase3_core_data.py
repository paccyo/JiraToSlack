"""
Phase 3のユニットテスト: コアデータ取得
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

from prototype.local_cli.core.phase3_core_data import (
    fetch_core_data,
    CoreDataError,
    _is_status_done,
    _extract_times_from_changelog,
)
from prototype.local_cli.core.types import (
    AuthContext,
    JiraMetadata,
    BoardMetadata,
    SprintMetadata,
)


class TestIsStatusDone:
    """ステータス完了判定のテスト"""
    
    def test_is_status_done_true(self):
        """完了ステータスの判定"""
        status = {
            "name": "Done",
            "statusCategory": {"key": "done"}
        }
        assert _is_status_done(status) is True
    
    def test_is_status_done_false_new(self):
        """未着手ステータスの判定"""
        status = {
            "name": "To Do",
            "statusCategory": {"key": "new"}
        }
        assert _is_status_done(status) is False
    
    def test_is_status_done_false_indeterminate(self):
        """進行中ステータスの判定"""
        status = {
            "name": "In Progress",
            "statusCategory": {"key": "indeterminate"}
        }
        assert _is_status_done(status) is False
    
    def test_is_status_done_none_status(self):
        """ステータスがNoneの場合"""
        assert _is_status_done(None) is False
    
    def test_is_status_done_no_category(self):
        """カテゴリがない場合"""
        status = {"name": "Unknown"}
        assert _is_status_done(status) is False


class TestExtractTimesFromChangelog:
    """changelog解析のテスト"""
    
    def test_extract_times_success(self):
        """正常なchangelog解析"""
        changelog = {
            "histories": [
                {
                    "created": "2025-01-01T10:00:00.000Z",
                    "items": [
                        {
                            "field": "status",
                            "toString": "In Progress"
                        }
                    ]
                },
                {
                    "created": "2025-01-05T15:00:00.000Z",
                    "items": [
                        {
                            "field": "status",
                            "toString": "Done"
                        }
                    ]
                }
            ]
        }
        
        started_at, completed_at = _extract_times_from_changelog(changelog)
        
        assert started_at == "2025-01-01T10:00:00.000Z"
        assert completed_at == "2025-01-05T15:00:00.000Z"
    
    def test_extract_times_japanese_status(self):
        """日本語ステータスの解析"""
        changelog = {
            "histories": [
                {
                    "created": "2025-01-01T10:00:00.000Z",
                    "items": [
                        {
                            "field": "status",
                            "toString": "作業中"
                        }
                    ]
                },
                {
                    "created": "2025-01-05T15:00:00.000Z",
                    "items": [
                        {
                            "field": "status",
                            "toString": "完了"
                        }
                    ]
                }
            ]
        }
        
        started_at, completed_at = _extract_times_from_changelog(changelog)
        
        assert started_at == "2025-01-01T10:00:00.000Z"
        assert completed_at == "2025-01-05T15:00:00.000Z"
    
    def test_extract_times_no_histories(self):
        """履歴がない場合"""
        changelog = {"histories": []}
        
        started_at, completed_at = _extract_times_from_changelog(changelog)
        
        assert started_at is None
        assert completed_at is None
    
    def test_extract_times_empty_changelog(self):
        """空のchangelog"""
        started_at, completed_at = _extract_times_from_changelog({})
        
        assert started_at is None
        assert completed_at is None
    
    def test_extract_times_no_status_changes(self):
        """ステータス変更がない場合"""
        changelog = {
            "histories": [
                {
                    "created": "2025-01-01T10:00:00.000Z",
                    "items": [
                        {
                            "field": "summary",
                            "toString": "New summary"
                        }
                    ]
                }
            ]
        }
        
        started_at, completed_at = _extract_times_from_changelog(changelog)
        
        assert started_at is None
        assert completed_at is None


class TestFetchCoreData:
    """fetch_core_data統合テスト"""
    
    @patch('prototype.local_cli.core.phase3_core_data.JiraClient')
    @patch('prototype.local_cli.core.phase3_core_data._fetch_parent_tasks')
    def test_fetch_core_data_success(self, mock_fetch_parents, mock_jira_client_class):
        """正常なコアデータ取得"""
        # JiraClientのモック
        mock_client = MagicMock()
        mock_client.domain = "https://test.atlassian.net"
        mock_jira_client_class.return_value = mock_client
        
        # 親タスクのモックデータ
        mock_parent_issues = [
            {
                "key": "PROJ-1",
                "fields": {
                    "summary": "Parent Task 1",
                    "assignee": {"displayName": "Taro"},
                    "subtasks": [
                        {"id": "10001", "key": "PROJ-1-SUB1"},
                        {"id": "10002", "key": "PROJ-1-SUB2"}
                    ]
                }
            }
        ]
        
        mock_fetch_parents.return_value = (200, mock_parent_issues, "")
        
        # サブタスクAPIのモック
        def mock_api_get(url, params=None):
            if "/issue/10001" in url or "PROJ-1-SUB1" in url:
                return (200, {
                    "key": "PROJ-1-SUB1",
                    "fields": {
                        "summary": "Subtask 1",
                        "status": {"name": "Done", "statusCategory": {"key": "done"}},
                        "assignee": {"displayName": "Taro"},
                        "issuetype": {"name": "Sub-task"},
                        "created": "2025-01-01T00:00:00.000Z",
                        "resolutiondate": "2025-01-05T00:00:00.000Z",
                        "customfield_10016": 3.0
                    },
                    "changelog": {"histories": []}
                }, "")
            elif "/issue/10002" in url or "PROJ-1-SUB2" in url:
                return (200, {
                    "key": "PROJ-1-SUB2",
                    "fields": {
                        "summary": "Subtask 2",
                        "status": {"name": "To Do", "statusCategory": {"key": "new"}},
                        "assignee": {"displayName": "Taro"},
                        "issuetype": {"name": "Sub-task"},
                        "created": "2025-01-01T00:00:00.000Z",
                        "resolutiondate": None,
                        "customfield_10016": 2.0
                    },
                    "changelog": {"histories": []}
                }, "")
            return (404, None, "Not found")
        
        mock_client.api_get = Mock(side_effect=mock_api_get)
        
        # メタデータ
        auth = AuthContext(
            domain="https://test.atlassian.net",
            auth=HTTPBasicAuth("test@example.com", "token")
        )
        
        metadata = JiraMetadata(
            board=BoardMetadata(
                board={"id": 123},
                board_id=123,
                project_key="PROJ",
                boards_count=1
            ),
            sprint=SprintMetadata(
                sprint={"id": 789},
                sprint_id=789,
                sprint_name="Sprint 1",
                sprint_start=None,
                sprint_end=None,
                active_sprints_count=1
            ),
            project_key="PROJ",
            story_points_field="customfield_10016"
        )
        
        # 実行
        result = fetch_core_data(auth, metadata, enable_logging=False)
        
        # 検証
        assert result.totals.subtasks == 2
        assert result.totals.done == 1
        assert result.totals.not_done == 1
        assert len(result.parents) == 1
        assert result.parents[0].key == "PROJ-1"
        assert len(result.parents[0].subtasks) == 2
    
    @patch('prototype.local_cli.core.phase3_core_data.JiraClient')
    @patch('prototype.local_cli.core.phase3_core_data._fetch_parent_tasks')
    def test_fetch_core_data_no_subtasks(self, mock_fetch_parents, mock_jira_client_class):
        """サブタスクがない場合"""
        mock_client = MagicMock()
        mock_jira_client_class.return_value = mock_client
        
        # サブタスクがない親タスク
        mock_parent_issues = [
            {
                "key": "PROJ-1",
                "fields": {
                    "summary": "Parent Task without subtasks",
                    "assignee": {"displayName": "Taro"},
                    "subtasks": []
                }
            }
        ]
        
        mock_fetch_parents.return_value = (200, mock_parent_issues, "")
        
        auth = AuthContext(
            domain="https://test.atlassian.net",
            auth=HTTPBasicAuth("test@example.com", "token")
        )
        
        metadata = JiraMetadata(
            board=BoardMetadata(
                board={"id": 123},
                board_id=123,
                project_key="PROJ",
                boards_count=1
            ),
            sprint=SprintMetadata(
                sprint={"id": 789},
                sprint_id=789,
                sprint_name="Sprint 1",
                sprint_start=None,
                sprint_end=None,
                active_sprints_count=1
            ),
            project_key="PROJ",
            story_points_field="customfield_10016"
        )
        
        result = fetch_core_data(auth, metadata)
        
        # サブタスクがないのでparentsは空
        assert result.totals.subtasks == 0
        assert result.totals.done == 0
        assert len(result.parents) == 0
    
    @patch('prototype.local_cli.core.phase3_core_data.JiraClient')
    @patch('prototype.local_cli.core.phase3_core_data._fetch_parent_tasks')
    def test_fetch_core_data_fetch_failure(self, mock_fetch_parents, mock_jira_client_class):
        """親タスク取得失敗時のエラー"""
        mock_client = MagicMock()
        mock_jira_client_class.return_value = mock_client
        
        # 親タスク取得を失敗させる
        mock_fetch_parents.return_value = (404, None, "Sprint not found")
        
        auth = AuthContext(
            domain="https://test.atlassian.net",
            auth=HTTPBasicAuth("test@example.com", "token")
        )
        
        metadata = JiraMetadata(
            board=BoardMetadata(
                board={"id": 123},
                board_id=123,
                project_key="PROJ",
                boards_count=1
            ),
            sprint=SprintMetadata(
                sprint={"id": 789},
                sprint_id=789,
                sprint_name="Sprint 1",
                sprint_start=None,
                sprint_end=None,
                active_sprints_count=1
            ),
            project_key="PROJ",
            story_points_field="customfield_10016"
        )
        
        with pytest.raises(CoreDataError, match="親タスク取得に失敗しました"):
            fetch_core_data(auth, metadata)
