import json
from pathlib import Path
import pytest
import requests
from prototype.local_cli.lib.jira_client import JiraClient


def _mk_url(domain, path):
    return f"{domain}{path}"


@pytest.mark.usefixtures("fake_env")
def test_burndown_query_mocks(monkeypatch):
    # Monkeypatch JiraClient methods directly
    sprint = {"id": 123, "name": "Sprint 1", "startDate": "2025-09-01T00:00:00+09:00", "endDate": "2025-09-05T00:00:00+09:00"}
    monkeypatch.setattr(JiraClient, "resolve_board", lambda self: (200, {"id": 1, "name": "Board"}, ""), raising=True)
    monkeypatch.setattr(JiraClient, "resolve_active_sprint", lambda self, board_id=None: (200, sprint, ""), raising=True)
    monkeypatch.setattr(JiraClient, "resolve_story_points_field", lambda self: "customfield_10016", raising=True)
    monkeypatch.setattr(JiraClient, "search_paginated", lambda self, jql, fields, batch=100: (200, [], ""), raising=True)
    monkeypatch.setattr(JiraClient, "api_get", lambda self, url, params=None: (200, {}, ""), raising=True)

    # import and run main
    import importlib
    import sys as _sys
    mod = importlib.import_module("prototype.local_cli.queries.jira_q_burndown")
    monkeypatch.setattr(_sys, 'argv', ['__main__.py'])
    rc = mod.main()
    assert rc == 0


@pytest.mark.usefixtures("fake_env")
def test_velocity_query_mocks(monkeypatch):
    closed_sprints = {"values": [{"id": 10, "name": "S-10"}, {"id": 9, "name": "S-9"}]}
    monkeypatch.setattr(JiraClient, "resolve_board", lambda self: (200, {"id": 1, "name": "Board"}, ""), raising=True)
    def fake_api_get(self, url, params=None):
        if url.endswith("/rest/agile/1.0/board/1/sprint") and (params or {}).get("state") == "closed":
            return 200, closed_sprints, ""
        if url.endswith("/rest/api/3/field"):
            return 200, [{"id": "customfield_10016", "schema": {"custom": "com.pyxis.greenhopper.jira:jsw-story-points"}}], ""
        return 200, {}, ""
    monkeypatch.setattr(JiraClient, "api_get", fake_api_get, raising=True)
    def fake_search_paginated(self, jql, fields, batch=100):
        if "Sprint=10" in jql:
            return 200, [{"fields": {"customfield_10016": 5}}], ""
        if "Sprint=9" in jql:
            return 200, [{"fields": {"customfield_10016": 3}}], ""
        return 200, [], ""
    monkeypatch.setattr(JiraClient, "search_paginated", fake_search_paginated, raising=True)
    monkeypatch.setattr(JiraClient, "resolve_story_points_field", lambda self: "customfield_10016", raising=True)

    import importlib
    import sys as _sys
    mod = importlib.import_module("prototype.local_cli.queries.jira_q_velocity_history")
    monkeypatch.setattr(_sys, 'argv', ['__main__.py'])
    rc = mod.main()
    assert rc == 0