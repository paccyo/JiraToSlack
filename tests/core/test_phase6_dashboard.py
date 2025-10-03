"""
Phase 6: ダッシュボード描画のテスト（シンプル版）
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

from prototype.local_cli.core.phase6_dashboard import (
    render_dashboard,
    DashboardError,
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
    temp_dir = tempfile.mkdtemp(prefix="test_dashboard_")
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
    board = {
        "id": 123,
        "name": "Test Board"
    }
    sprint = {
        "id": 456,
        "name": "Sprint 1",
        "state": "active"
    }
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
            "due_soon": 0,
            "high_priority_todo": 0,
            "unassigned": 0,
        },
        risks={},
        evidence=None,
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
# ダッシュボード描画のテスト
# ============================================================

def test_render_dashboard_basic(
    config,
    metadata,
    core_data,
    metrics,
    temp_output_dir
):
    """基本的なダッシュボード描画"""
    # モックのdraw_png関数
    mock_draw_png = MagicMock()
    
    # 描画実行（関数をインジェクト）
    output_path = render_dashboard(
        config, metadata, core_data, metrics, 
        enable_logging=True,
        _draw_png_func=mock_draw_png
    )
    
    # 結果検証
    assert output_path == temp_output_dir / "sprint_overview.png"
    assert mock_draw_png.called
    
    # draw_pngの引数を検証
    call_args = mock_draw_png.call_args
    assert call_args is not None
    assert call_args[1]["data"] == core_data.to_dict()
    assert call_args[1]["extras"] == metrics.to_dict()
    assert call_args[1]["target_done_rate"] == 0.8


def test_render_dashboard_with_ai_summary(
    config,
    metadata,
    core_data,
    metrics,
    ai_summary,
    temp_output_dir
):
    """AI要約付きダッシュボード描画"""
    # モックのdraw_png関数
    mock_draw_png = MagicMock()
    
    # 描画実行
    output_path = render_dashboard(
        config, metadata, core_data, metrics, ai_summary,
        enable_logging=True,
        _draw_png_func=mock_draw_png
    )
    
    # 結果検証
    assert output_path == temp_output_dir / "sprint_overview.png"
    assert mock_draw_png.called
    
    # AI要約がextrasに含まれていることを確認
    call_args = mock_draw_png.call_args
    extras = call_args[1]["extras"]
    assert "ai_full_text" in extras
    assert extras["ai_full_text"] == "## 🎯 結論\n完了率50% - 注意⚠️"
    assert "ai_reasons" in extras
    assert extras["ai_reasons"] == {"TEST-101": "優先度高"}


def test_render_dashboard_without_ai_summary(
    config,
    metadata,
    core_data,
    metrics,
    temp_output_dir
):
    """AI要約なしダッシュボード描画"""
    # モックのdraw_png関数
    mock_draw_png = MagicMock()
    
    # 描画実行
    output_path = render_dashboard(
        config, metadata, core_data, metrics, None,
        enable_logging=False,
        _draw_png_func=mock_draw_png
    )
    
    # 結果検証
    assert output_path == temp_output_dir / "sprint_overview.png"
    assert mock_draw_png.called
    
    # AI要約がextrasに含まれていないことを確認
    call_args = mock_draw_png.call_args
    extras = call_args[1]["extras"]
    assert "ai_full_text" not in extras or extras.get("ai_full_text") is None


def test_render_dashboard_draw_png_error(
    config,
    metadata,
    core_data,
    metrics
):
    """draw_png関数がエラーを起こす場合"""
    # モックのdraw_png関数がエラーを起こす
    mock_draw_png = MagicMock(side_effect=Exception("描画エラー"))
    
    # エラーが発生することを確認
    with pytest.raises(DashboardError) as exc_info:
        render_dashboard(
            config, metadata, core_data, metrics,
            _draw_png_func=mock_draw_png
        )
    
    assert "ダッシュボード描画エラー" in str(exc_info.value)


def test_render_dashboard_creates_output_dir(
    metadata,
    core_data,
    metrics
):
    """出力ディレクトリが自動作成されることを確認"""
    # 存在しないディレクトリを指定
    temp_dir = tempfile.mkdtemp(prefix="test_dashboard_parent_")
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
        
        # モックのdraw_png関数
        mock_draw_png = MagicMock()
        
        # 描画実行
        output_path = render_dashboard(
            config, metadata, core_data, metrics,
            _draw_png_func=mock_draw_png
        )
        
        # ディレクトリが作成されたことを確認
        assert nonexistent_dir.exists()
        assert output_path == nonexistent_dir / "sprint_overview.png"
        
    finally:
        # クリーンアップ
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
