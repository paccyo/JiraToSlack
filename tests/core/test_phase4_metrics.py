"""
Phase 4: メトリクス収集のテスト
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from prototype.local_cli.core.phase4_metrics import (
    collect_metrics,
    _build_metric_queries,
    _execute_single_query,
    _aggregate_metrics,
    _calculate_assignee_workload,
    _calculate_time_in_status,
    MetricsError,
)
from prototype.local_cli.core.types import (
    AuthContext,
    JiraMetadata,
    BoardMetadata,
    SprintMetadata,
    CoreData,
    ParentTask,
    SubtaskData,
    TaskTotals,
)


@pytest.fixture
def auth_context():
    """認証コンテキストのフィクスチャ"""
    from requests.auth import HTTPBasicAuth
    return AuthContext(
        domain="https://test.atlassian.net",
        auth=HTTPBasicAuth("test@example.com", "token")
    )


@pytest.fixture
def metadata():
    """メタデータのフィクスチャ"""
    board = BoardMetadata(
        board={"id": 123, "name": "Test Board"},
        board_id=123,
        project_key="TEST",
        boards_count=1,
    )
    sprint = SprintMetadata(
        sprint={"id": 456, "name": "Sprint 1", "state": "active"},
        sprint_id=456,
        sprint_name="Sprint 1",
        sprint_start=None,
        sprint_end=None,
        active_sprints_count=1,
    )
    return JiraMetadata(
        board=board,
        sprint=sprint,
        project_key="TEST",
        story_points_field="customfield_10016"
    )


@pytest.fixture
def core_data():
    """コアデータのフィクスチャ"""
    subtasks = [
        SubtaskData(
            key="TEST-101",
            summary="Subtask 1",
            done=True,
            assignee="user1@example.com",
            status="Done",
            priority="High",
            story_points=3.0,
            created="2024-01-01T10:00:00.000+0900",
            started_at="2024-01-02T10:00:00.000+0900",
            completed_at="2024-01-03T10:00:00.000+0900",
            due_date="2024-01-05",
        ),
        SubtaskData(
            key="TEST-102",
            summary="Subtask 2",
            done=False,
            assignee="user2@example.com",
            status="In Progress",
            priority="High",
            story_points=5.0,
            created="2024-01-01T11:00:00.000+0900",
            started_at="2024-01-02T11:00:00.000+0900",
            completed_at=None,
            due_date="2024-01-06",
        ),
        SubtaskData(
            key="TEST-103",
            summary="Subtask 3",
            done=False,
            assignee=None,
            status="To Do",
            priority="Low",
            story_points=2.0,
            created="2024-01-01T12:00:00.000+0900",
            started_at=None,
            completed_at=None,
            due_date="2024-01-10",
        ),
    ]
    
    parent = ParentTask(
        key="TEST-100",
        summary="Parent Task",
        assignee="user1@example.com",
        subtasks=subtasks,
    )
    
    totals = TaskTotals(subtasks=3, done=1, not_done=2)
    
    return CoreData(parents=[parent], totals=totals)


# ============================================================
# クエリ構築のテスト
# ============================================================

def test_build_metric_queries_basic():
    """基本的なクエリ構築"""
    queries = _build_metric_queries(sprint_id=456, project_key="TEST")
    
    assert len(queries) == 6
    assert queries[0].name == "overdue"
    assert queries[1].name == "due_soon"
    assert queries[2].name == "high_priority_todo"
    assert queries[3].name == "unassigned"
    assert queries[4].name == "project_total"
    assert queries[5].name == "project_open"


def test_build_metric_queries_sprint_id_in_jql():
    """JQLにスプリントIDが含まれている"""
    queries = _build_metric_queries(sprint_id=999, project_key="TEST")
    
    assert "Sprint=999" in queries[0].jql
    assert "Sprint=999" in queries[1].jql
    assert "Sprint=999" in queries[2].jql


def test_build_metric_queries_project_key_in_jql():
    """JQLにプロジェクトキーが含まれている"""
    queries = _build_metric_queries(sprint_id=456, project_key="DEMO")
    
    assert "project=DEMO" in queries[4].jql
    assert "project=DEMO" in queries[5].jql


def test_due_soon_jql_uses_quoted_offset(monkeypatch):
    """期限間近クエリでは+Ndが引用符付きで出力される"""
    monkeypatch.setenv("DUE_SOON_DAYS", "5")
    queries = _build_metric_queries(sprint_id=123, project_key="KEY")

    assert 'endOfDay("+5d")' in queries[1].jql


# ============================================================
# 単一クエリ実行のテスト
# ============================================================

def test_execute_single_query_success():
    """単一クエリの成功"""
    mock_client = MagicMock()
    mock_client.count_jql.return_value = (200, 42, None)
    
    from prototype.local_cli.core.phase4_metrics import MetricQuery
    query = MetricQuery(
        name="test_query",
        jql="Sprint=456",
        description="Test query"
    )
    
    count = _execute_single_query(mock_client, query)
    
    assert count == 42
    mock_client.count_jql.assert_called_once_with("Sprint=456", batch=500)


def test_execute_single_query_failure():
    """単一クエリの失敗（0を返す）"""
    mock_client = MagicMock()
    mock_client.count_jql.return_value = (500, None, "Server error")
    
    from prototype.local_cli.core.phase4_metrics import MetricQuery
    query = MetricQuery(
        name="test_query",
        jql="Sprint=456",
        description="Test query"
    )
    
    count = _execute_single_query(mock_client, query)
    
    assert count == 0


# ============================================================
# メトリクス集約のテスト
# ============================================================

def test_aggregate_metrics_kpis(core_data):
    """KPIの集約"""
    query_results = {
        "overdue": 5,
        "due_soon": 3,
        "high_priority_todo": 8,
        "unassigned": 2,
        "project_total": 100,
        "project_open": 60,
    }
    
    metrics = _aggregate_metrics(query_results, core_data)
    
    assert metrics.kpis["sprintTotal"] == 3
    assert metrics.kpis["sprintDone"] == 1
    assert metrics.kpis["sprintOpen"] == 2
    assert metrics.kpis["projectTotal"] == 100
    assert metrics.kpis["projectOpenTotal"] == 60
    assert metrics.kpis["overdue"] == 5
    assert metrics.kpis["dueSoon"] == 3
    assert metrics.kpis["highPriorityTodo"] == 8
    assert metrics.kpis["unassignedCount"] == 2


def test_aggregate_metrics_risks(core_data):
    """リスク情報の集約"""
    query_results = {
        "overdue": 5,
        "due_soon": 3,
        "high_priority_todo": 8,
    }
    
    metrics = _aggregate_metrics(query_results, core_data)
    
    assert metrics.risks["overdue"] == 5
    assert metrics.risks["dueSoon"] == 3
    assert metrics.risks["highPriorityTodo"] == 8


def test_aggregate_metrics_with_missing_results(core_data):
    """一部の結果が欠けている場合（デフォルト0）"""
    query_results = {
        "overdue": 5,
    }
    
    metrics = _aggregate_metrics(query_results, core_data)
    
    assert metrics.kpis["overdue"] == 5
    assert metrics.kpis["dueSoon"] == 0
    assert metrics.kpis["highPriorityTodo"] == 0
    assert metrics.kpis["unassignedCount"] == 0


# ============================================================
# 担当者ワークロード計算のテスト
# ============================================================

def test_calculate_assignee_workload(core_data):
    """担当者別ワークロードの計算"""
    workload = _calculate_assignee_workload(core_data)
    
    assert len(workload) == 3
    
    # user1
    assert "user1@example.com" in workload
    assert workload["user1@example.com"]["subtasks"] == 1
    assert workload["user1@example.com"]["done"] == 1
    assert workload["user1@example.com"]["storyPoints"] == 3.0
    
    # user2
    assert "user2@example.com" in workload
    assert workload["user2@example.com"]["subtasks"] == 1
    assert workload["user2@example.com"]["done"] == 0
    assert workload["user2@example.com"]["storyPoints"] == 5.0
    
    # 未割り当て
    assert "(未割り当て)" in workload
    assert workload["(未割り当て)"]["subtasks"] == 1
    assert workload["(未割り当て)"]["done"] == 0
    assert workload["(未割り当て)"]["storyPoints"] == 2.0


def test_calculate_assignee_workload_empty():
    """サブタスクがない場合"""
    core_data = CoreData(parents=[], totals=TaskTotals(subtasks=0, done=0, not_done=0))
    workload = _calculate_assignee_workload(core_data)
    
    assert len(workload) == 0


# ============================================================
# 統合テスト
# ============================================================

def test_collect_metrics_integration(auth_context, metadata, core_data, monkeypatch):
    """メトリクス収集の統合テスト"""
    mock_client = MagicMock()
    mock_client.domain = auth_context.domain
    mock_client.count_jql.side_effect = [
        (200, 5, None),   # overdue
        (200, 3, None),   # due_soon
        (200, 8, None),   # high_priority_todo
        (200, 2, None),   # unassigned
        (200, 100, None), # project_total
        (200, 60, None),  # project_open
    ]
    mock_client.search_paginated.return_value = (200, [], "")
    
    # JiraClientをモックに置き換え
    def mock_jira_client_init(self):
        return mock_client
    
    import sys
    from types import ModuleType
    
    # Loderモジュールをモック
    mock_loder = ModuleType('Loder')
    mock_jira_client_module = ModuleType('Loder.jira_client')
    mock_jira_client_module.JiraClient = lambda: mock_client
    mock_loder.jira_client = mock_jira_client_module
    sys.modules['Loder'] = mock_loder
    sys.modules['Loder.jira_client'] = mock_jira_client_module
    
    metrics = collect_metrics(auth_context, metadata, core_data, enable_logging=True)
    
    # KPIの確認
    assert metrics.kpis["sprintTotal"] == 3
    assert metrics.kpis["overdue"] == 5
    assert metrics.kpis["dueSoon"] == 3
    
    # リスクの確認
    assert metrics.risks["overdue"] == 5
    
    # ワークロードの確認
    assert len(metrics.assignee_workload) == 3


def test_collect_metrics_with_query_failures(auth_context, metadata, core_data):
    """一部のクエリが失敗した場合"""
    mock_client = MagicMock()
    mock_client.domain = auth_context.domain
    mock_client.count_jql.side_effect = [
        (200, 5, None),       # overdue
        (500, None, "Error"), # due_soon (失敗)
        (200, 8, None),       # high_priority_todo
        (500, None, "Error"), # unassigned (失敗)
        (200, 100, None),     # project_total
        (200, 60, None),      # project_open
    ]
    mock_client.search_paginated.return_value = (200, [], "")
    
    # JiraClientをモックに置き換え
    import sys
    from types import ModuleType
    
    # Loderモジュールをモック
    mock_loder = ModuleType('Loder')
    mock_jira_client_module = ModuleType('Loder.jira_client')
    mock_jira_client_module.JiraClient = lambda: mock_client
    mock_loder.jira_client = mock_jira_client_module
    sys.modules['Loder'] = mock_loder
    sys.modules['Loder.jira_client'] = mock_jira_client_module
    
    metrics = collect_metrics(auth_context, metadata, core_data, enable_logging=False)
    
    # 成功したクエリ
    assert metrics.kpis["overdue"] == 5
    assert metrics.kpis["highPriorityTodo"] == 8
    
    # 失敗したクエリ（0になる）
    assert metrics.kpis["dueSoon"] == 0
    assert metrics.kpis["unassignedCount"] == 0


def test_extract_evidence_enriched_fields(metadata, core_data, monkeypatch):
    """Evidence抽出が拡張フィールドを付与する"""
    from prototype.local_cli.core import phase4_metrics

    class _FixedDateTime(datetime):  # type: ignore
        @classmethod
        def now(cls, tz=None):
            tz = tz or timezone.utc
            return cls(2024, 1, 5, 0, 0, tzinfo=tz)

    monkeypatch.setattr(phase4_metrics, "datetime", _FixedDateTime)

    evidences = phase4_metrics._extract_evidence(core_data, {}, metadata, top_n=5)
    assert evidences is not None
    assert len(evidences) >= 2

    example = evidences[0]
    assert example["status"]
    assert example["assignee"]
    assert "reason" in example and example["reason"]
    assert "why" in example and example["why"]
    assert "days" in example


def test_calculate_time_in_status_basic():
    """Time-in-Status の基礎集計"""
    sprint = SprintMetadata(
        sprint={"id": 456, "name": "Sprint 1", "state": "active"},
        sprint_id=456,
        sprint_name="Sprint 1",
        sprint_start="2024-01-01T00:00:00+09:00",
        sprint_end="2024-01-04T00:00:00+09:00",
        active_sprints_count=1,
    )
    board = BoardMetadata(
        board={"id": 123, "name": "Test Board"},
        board_id=123,
        project_key="TEST",
        boards_count=1,
    )
    metadata_with_dates = JiraMetadata(
        board=board,
        sprint=sprint,
        project_key="TEST",
        story_points_field="customfield_10016",
    )

    mock_client = MagicMock()
    mock_client.domain = "https://example.atlassian.net"
    mock_client.search_paginated.return_value = (200, [{"id": "1", "key": "TEST-1"}], "")
    mock_client.api_get.return_value = (
        200,
        {
            "fields": {
                "status": {"name": "Done"},
                "created": "2023-12-31T00:00:00+09:00",
            },
            "changelog": {
                "histories": [
                    {
                        "created": "2024-01-02T00:00:00+09:00",
                        "items": [{"field": "status", "toString": "In Progress"}],
                    },
                    {
                        "created": "2024-01-03T00:00:00+09:00",
                        "items": [{"field": "status", "toString": "Review"}],
                    },
                    {
                        "created": "2024-01-04T00:00:00+09:00",
                        "items": [{"field": "status", "toString": "Done"}],
                    },
                ]
            },
        },
        "",
    )

    result = _calculate_time_in_status(
        mock_client,
        metadata_with_dates,
        unit="days",
        scope="sprint",
        enable_logging=False,
    )

    assert result is not None
    tot = result["totalByStatus"]
    assert pytest.approx(1.0, rel=1e-3) == tot["In Progress"]
    assert pytest.approx(1.0, rel=1e-3) == tot["Review"]
    issue_entry = result["perIssue"][0]
    assert pytest.approx(1.0, rel=1e-3) == issue_entry["byStatus"]["Review"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
