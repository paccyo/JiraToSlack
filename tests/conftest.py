import os
import json
import tempfile
from pathlib import Path
import contextlib
import shutil
import types

import pytest


@pytest.fixture()
def temp_output_dir(monkeypatch):
    d = tempfile.mkdtemp(prefix="jtstest-")
    monkeypatch.setenv("OUTPUT_DIR", d)
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def fake_env(monkeypatch):
    # Minimal env to bypass JiraClient _load_env exits in tests that import queries indirectly
    monkeypatch.setenv("JIRA_DOMAIN", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "x")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")
    return True


@contextlib.contextmanager
def patch_requests_session_get(mocker, responses):
    import requests
    orig = requests.Session.get
    def _fake(self, url, auth=None, params=None, timeout=None):
        key = (url, json.dumps(params or {}, sort_keys=True))
        if key in responses:
            status, payload = responses[key]
            class R:
                status_code = status
                def json(self):
                    return payload
                @property
                def text(self):
                    return json.dumps(payload)
            return R()
        # default 404
        class R2:
            status_code = 404
            def json(self):
                return {"error": "not found"}
            @property
            def text(self):
                return "not found"
        return R2()
    mocker.patch.object(requests.Session, 'get', _fake)
    try:
        yield
    finally:
        pass
