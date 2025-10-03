"""
Phase 7: ファイル出力のテスト
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path

from prototype.local_cli.core.phase7_output import (
    generate_markdown_report,
    export_tasks_json,
    export_metrics_json,
    generate_all_outputs,
    OutputError,
    OutputPaths,
)
from prototype.local_cli.core.types import (
    EnvironmentConfig,
    JiraMetadata,
    BoardMetadata,
    SprintMetadata,
    CoreData,
    ParentTask,
    SubtaskData,
    TaskTotals,
    MetricsCollection,
    AISummary,
)


@pytest.fixture
def temp_output_dir():
    """一時出力ディレクトリ"""
    temp_dir = tempfile.mkdtemp(prefix="test_output_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def config(temp_output_dir):
    """環境設定のフィクスチャ"""
    return EnvironmentConfig(
        jira_domain="https://test.atlassian.net",
        jira_email="test@example.com",
        jira_api_token="token123",
        output_dir=str(temp_output_dir),
        target_done_rate=0.8,
        axis_mode="percent",
        gemini_api_key="test-api-key",
        gemini_model="gemini-2.5-flash-lite",
        gemini_disable=False,
    )


@pytest.fixture
def metadata():
    """Jiraメタデータのフィクスチャ"""
    board = {"id": 123, "name": "Test Board"}
    sprint = {"id": 456, "name": "Sprint 1", "state": "active"}
    return JiraMetadata(
        board=BoardMetadata(
            board=board,
            board_id=123,
            project_key="TEST",
            boards_count=1
        ),
        sprint=SprintMetadata(
            sprint=sprint,
            sprint_id=456,
            sprint_name="Sprint 1",
            sprint_start="2024-01-01",
            sprint_end="2024-01-14",
            active_sprints_count=1
        ),
        project_key="TEST",
        story_points_field="customfield_10016"
    )


@pytest.fixture
def core_data():
    """コアデータのフィクスチャ"""
    return CoreData(
        parents=[
            ParentTask(
                key="TEST-100",
                summary="Parent Task",
                assignee="user1@example.com",
                subtasks=[
                    SubtaskData(
                        key="TEST-101",
                        summary="Subtask 1",
                        assignee="user1@example.com",
                        status="完了",
                        done=True,
                        started_at="2024-01-02T10:00:00.000+0900",
                        completed_at="2024-01-02T12:00:00.000+0900"
                    ),
                    SubtaskData(
                        key="TEST-102",
                        summary="Subtask 2",
                        assignee="user2@example.com",
                        status="進行中",
                        done=False,
                        started_at="2024-01-02T11:00:00.000+0900",
                        completed_at=None
                    )
                ]
            )
        ],
        totals=TaskTotals(
            subtasks=2,
            done=1,
            not_done=1
        )
    )


@pytest.fixture
def metrics():
    """メトリクスのフィクスチャ"""
    return MetricsCollection(
        burndown=None,
        velocity=None,
        project_sprint_count=None,
        status_counts=None,
        time_in_status=None,
        workload=None,
        kpis={
            "overdue": 0,
            "due_soon": 1,
            "high_priority_todo": 0,
        },
        risks={
            "overdue": 0,
            "due_soon": 1,
            "high_priority_todo": 0,
        },
        evidence=[
            {
                "key": "TEST-101",
                "summary": "Test Issue",
                "status": "完了",
                "days": 2.5,
                "assignee": "user1@example.com",
                "why": "テスト用",
                "link": "https://test.atlassian.net/browse/TEST-101"
            }
        ],
        project_subtask_count=None,
        assignee_workload={
            "user1@example.com": {"subtasks": 1, "done": 1},
            "user2@example.com": {"subtasks": 1, "done": 0}
        }
    )


@pytest.fixture
def ai_summary():
    """AI要約のフィクスチャ"""
    return AISummary(
        full_text="## 🎯 結論\n完了率50% - 注意⚠️",
        evidence_reasons={"TEST-101": "優先度高"}
    )


# ============================================================
# Markdownレポート生成のテスト
# ============================================================

def test_generate_markdown_report_basic(
    temp_output_dir,
    metadata,
    core_data,
    metrics
):
    """基本的なMarkdownレポート生成"""
    output_path = temp_output_dir / "test_report.md"
    
    generate_markdown_report(
        output_path,
        metadata,
        core_data,
        metrics,
        None,
        0.8,
        enable_logging=True
    )
    
    # ファイルが生成されていることを確認
    assert output_path.exists()
    
    # 内容を確認
    content = output_path.read_text(encoding="utf-8")
    assert "## 要約" in content
    assert "Sprint 1" in content
    assert "2 tasks" in content
    assert "Done 1" in content
    assert "## リスク" in content


def test_generate_markdown_report_with_ai_summary(
    temp_output_dir,
    metadata,
    core_data,
    metrics,
    ai_summary
):
    """AI要約付きMarkdownレポート生成"""
    output_path = temp_output_dir / "test_report.md"
    
    generate_markdown_report(
        output_path,
        metadata,
        core_data,
        metrics,
        ai_summary,
        0.8
    )
    
    # ファイルが生成されていることを確認
    assert output_path.exists()
    
    # AI要約が含まれていることを確認
    content = output_path.read_text(encoding="utf-8")
    assert "## AI要約 (Gemini)" in content
    assert "完了率50%" in content


def test_generate_markdown_report_with_risks(
    temp_output_dir,
    metadata,
    core_data
):
    """リスク情報付きMarkdownレポート生成"""
    output_path = temp_output_dir / "test_report.md"
    
    # リスクありのメトリクス
    metrics_with_risks = MetricsCollection(
        burndown=None,
        velocity=None,
        project_sprint_count=None,
        status_counts=None,
        time_in_status=None,
        workload=None,
        kpis={},
        risks={
            "overdue": 3,
            "due_soon": 2,
            "high_priority_todo": 1,
        },
        evidence=None,
        project_subtask_count=None,
        assignee_workload={}
    )
    
    generate_markdown_report(
        output_path,
        metadata,
        core_data,
        metrics_with_risks,
        None,
        0.8
    )
    
    # リスク情報が含まれていることを確認
    content = output_path.read_text(encoding="utf-8")
    assert "期限超過: 3件" in content
    assert "7日以内期限: 2件" in content
    assert "高優先度未着手: 1件" in content


# ============================================================
# タスクJSONエクスポートのテスト
# ============================================================

def test_export_tasks_json_basic(
    temp_output_dir,
    metadata,
    core_data
):
    """基本的なタスクJSONエクスポート"""
    output_path = temp_output_dir / "test_tasks.json"
    
    export_tasks_json(
        output_path,
        metadata,
        core_data,
        enable_logging=True
    )
    
    # ファイルが生成されていることを確認
    assert output_path.exists()
    
    # 内容を確認
    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert "sprint" in data
    assert data["sprint"]["name"] == "Sprint 1"
    assert "parents" in data
    assert len(data["parents"]) == 1
    assert "totals" in data
    assert data["totals"]["subtasks"] == 2


def test_export_tasks_json_structure(
    temp_output_dir,
    metadata,
    core_data
):
    """タスクJSON構造の検証"""
    output_path = temp_output_dir / "test_tasks.json"
    
    export_tasks_json(
        output_path,
        metadata,
        core_data
    )
    
    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # スプリント情報
    assert "startDate" in data["sprint"]
    assert "endDate" in data["sprint"]
    
    # 親タスク情報
    parent = data["parents"][0]
    assert "key" in parent
    assert "subtasks" in parent
    assert len(parent["subtasks"]) == 2


# ============================================================
# メトリクスJSONエクスポートのテスト
# ============================================================

def test_export_metrics_json_basic(
    temp_output_dir,
    config,
    metadata,
    core_data,
    metrics
):
    """基本的なメトリクスJSONエクスポート"""
    output_path = temp_output_dir / "test_metrics.json"
    
    export_metrics_json(
        output_path,
        metadata,
        core_data,
        metrics,
        config,
        enable_logging=True
    )
    
    # ファイルが生成されていることを確認
    assert output_path.exists()
    
    # 内容を確認
    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert "sprint" in data
    assert "totals" in data
    assert "doneRate" in data
    assert data["doneRate"] == 0.5
    assert data["targetDoneRate"] == 0.8
    assert data["axis"] == "percent"


def test_export_metrics_json_extras_available(
    temp_output_dir,
    config,
    metadata,
    core_data,
    metrics
):
    """extrasAvailableフィールドの検証"""
    output_path = temp_output_dir / "test_metrics.json"
    
    export_metrics_json(
        output_path,
        metadata,
        core_data,
        metrics,
        config
    )
    
    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert "extrasAvailable" in data
    extras = data["extrasAvailable"]
    assert "burndown" in extras
    assert "velocity" in extras
    assert extras["burndown"] == False
    assert extras["velocity"] == False


# ============================================================
# 統合テスト
# ============================================================

def test_generate_all_outputs_basic(
    config,
    metadata,
    core_data,
    metrics
):
    """すべてのファイル出力の統合テスト"""
    output_paths = generate_all_outputs(
        config,
        metadata,
        core_data,
        metrics,
        None,
        enable_logging=True
    )
    
    # OutputPathsが返されることを確認
    assert isinstance(output_paths, OutputPaths)
    
    # 各ファイルが生成されていることを確認
    assert output_paths.report_md.exists()
    assert output_paths.tasks_json.exists()
    assert output_paths.data_json.exists()
    
    # ファイル名を確認
    assert output_paths.report_md.name == "sprint_overview_report.md"
    assert output_paths.tasks_json.name == "sprint_overview_tasks.json"
    assert output_paths.data_json.name == "sprint_overview_data.json"


def test_generate_all_outputs_with_ai_summary(
    config,
    metadata,
    core_data,
    metrics,
    ai_summary
):
    """AI要約付き統合出力テスト"""
    output_paths = generate_all_outputs(
        config,
        metadata,
        core_data,
        metrics,
        ai_summary
    )
    
    # Markdownレポートにai要約が含まれていることを確認
    content = output_paths.report_md.read_text(encoding="utf-8")
    assert "## AI要約 (Gemini)" in content
    assert "完了率50%" in content


def test_generate_all_outputs_creates_directory(
    metadata,
    core_data,
    metrics
):
    """出力ディレクトリの自動作成テスト"""
    # 存在しないディレクトリを指定
    temp_dir = tempfile.mkdtemp(prefix="test_output_parent_")
    nonexistent_dir = Path(temp_dir) / "nonexistent" / "subdir"
    
    try:
        config = EnvironmentConfig(
            jira_domain="https://test.atlassian.net",
            jira_email="test@example.com",
            jira_api_token="token123",
            output_dir=str(nonexistent_dir),
            target_done_rate=0.8,
            axis_mode="percent",
            gemini_api_key="test-api-key",
            gemini_model="gemini-2.5-flash-lite",
            gemini_disable=False,
        )
        
        output_paths = generate_all_outputs(
            config,
            metadata,
            core_data,
            metrics
        )
        
        # ディレクトリが作成されたことを確認
        assert nonexistent_dir.exists()
        assert output_paths.report_md.exists()
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
