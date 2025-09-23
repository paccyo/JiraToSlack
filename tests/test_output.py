import io
import json
from pathlib import Path

import pytest
pytest.importorskip("PIL")
from PIL import Image


@pytest.mark.usefixtures("fake_env", "temp_output_dir")
def test_main_generates_outputs(monkeypatch, temp_output_dir):
    # Stub data providers in prototype/local_cli/main.py
    from prototype.local_cli import main as app

    # Disable external queries by overriding get_json_from_script* to return canned data
    def fake_get_json_from_script(script_path, env_extra=None):
        # Return minimal structure expected by draw_png
        return {
            "parents": [
                {"key": "EPIC-1", "subtasks": [
                    {"key": "PROJ-1", "done": True},
                    {"key": "PROJ-2", "done": False},
                    {"key": "PROJ-3", "done": False},
                ]}
            ],
            "totals": {"subtasks": 3, "done": 1}
        }

    def fake_get_json_from_script_args(script_path, args, env_extra=None):
        name = Path(script_path).name
        if name == "jira_q_burndown.py":
            return {
                "unit": "issues",
                "total": 3,
                "timeSeries": [
                    {"date": "2025-09-01", "remaining": 3},
                    {"date": "2025-09-02", "remaining": 2},
                    {"date": "2025-09-03", "remaining": 2},
                    {"date": "2025-09-04", "remaining": 1},
                ],
                "ideal": []
            }
        if name == "jira_q_velocity_history.py":
            return {
                "board": {"id": 1, "name": "Board"},
                "fieldId": "customfield_10016",
                "points": [
                    {"sprintId": 8, "sprintName": "S-8", "points": 5},
                    {"sprintId": 9, "sprintName": "S-9", "points": 3},
                ],
                "avgPoints": 4.0,
            }
        if name == "jira_q_status_counts.py":
            return {
                "total": 3,
                "byStatus": [
                    {"status": "To Do", "count": 2},
                    {"status": "Done", "count": 1},
                ],
            }
        if name == "jira_q_time_in_status.py":
            return {
                "window": {"unit": "days"},
                "perIssue": [
                    {"key": "PROJ-2", "byStatus": {"In Progress": 2.0, "Review": 1.0}},
                    {"key": "PROJ-3", "byStatus": {"To Do": 3.0}},
                ]
            }
        if name == "jira_q_assignee_workload.py":
            return {
                "byAssignee": [
                    {"name": "Alice", "notDone": 2},
                    {"name": "Bob", "notDone": 1},
                ]
            }
        # others
        return {}

    # Ensure OUTPUT_DIR is the temp dir and Gemini is disabled for determinism
    monkeypatch.setenv("OUTPUT_DIR", str(temp_output_dir))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("JIRA_PROJECT_KEY", raising=False)

    monkeypatch.setattr(app, "get_json_from_script", fake_get_json_from_script)
    monkeypatch.setattr(app, "get_json_from_script_args", fake_get_json_from_script_args)

    # Also stub network-dependent helpers in main to avoid HTTP
    monkeypatch.setattr(app, "resolve_board", lambda *a, **k: (404, None, ""))
    monkeypatch.setattr(app, "count_boards_for_project", lambda *a, **k: 1)
    monkeypatch.setattr(app, "count_active_sprints_for_board", lambda *a, **k: 1)
    monkeypatch.setattr(app, "resolve_active_sprint", lambda *a, **k: None)
    monkeypatch.setattr(app, "approximate_count", lambda *a, **k: (200, 0, ""))

    # Run
    rc = app.main()
    assert rc == 0

    # Check files
    png_path = temp_output_dir / "sprint_overview.png"
    json_path = temp_output_dir / "sprint_overview_data.json"
    md_path = temp_output_dir / "sprint_overview_report.md"
    assert png_path.exists(), "PNG が生成されていません"
    assert json_path.exists(), "JSON が生成されていません"
    assert md_path.exists(), "Markdown が生成されていません"

    # Validate PNG can be opened and has expected DPI and size
    with Image.open(png_path) as im:
        assert im.format == "PNG"
        dpi = im.info.get("dpi")
        if dpi:
            assert dpi[0] >= 150 and dpi[1] >= 150
        w, h = im.size
        assert w >= 1200 and h >= 800

    # Validate JSON content shape
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "targetDoneRate" in data and data["targetDoneRate"] is not None
    assert data.get("axis") in ("percent", "count")

    # Validate Markdown key sections
    md = md_path.read_text(encoding="utf-8")
    assert "## 要約" in md
    assert "## リスク" in md
    assert "## エビデンス" in md