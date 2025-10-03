from pathlib import Path

import pytest

from commands.jira.main import CommandJiraRepository


class QueryRecorder:
    def __init__(self) -> None:
        self.calls = []

    def get_json(self, script_path: str, extra_env: None | dict = None):
        script_name = Path(script_path).name
        self.calls.append(("noargs", script_name, tuple()))
        return {"script": script_name, "mode": "plain"}

    def get_json_with_args(self, script_path: str, args: list[str], extra_env: None | dict = None):
        script_name = Path(script_path).name
        self.calls.append(("args", script_name, tuple(args)))
        return {"script": script_name, "args": list(args)}


@pytest.fixture
def repo(monkeypatch):
    monkeypatch.setattr("commands.jira.main.ensure_env_loaded", lambda: None)
    monkeypatch.setattr(
        "prototype.local_cli.Loder.dotenv_loader.ensure_env_loaded",
        lambda: None,
    )
    recorder = QueryRecorder()
    repository = CommandJiraRepository(
        get_json=recorder.get_json,
        get_json_with_args=recorder.get_json_with_args,
        max_chars=200,
    )
    return recorder, repository


def test_help_lists_queries(repo):
    _, repository = repo
    message = repository.execute("")
    assert "利用可能なクエリ" in message
    assert "`burndown`" in message


def test_unknown_alias(repo):
    _, repository = repo
    message = repository.execute("unknown")
    assert "未対応" in message
    assert "`unknown`" in message


def test_due_soon_uses_env(monkeypatch, repo):
    recorder, repository = repo
    monkeypatch.setenv("DUE_SOON_DAYS", "3")
    repository.execute("due_soon")
    kind, script_name, args = recorder.calls[-1]
    assert kind == "args"
    assert script_name == "jira_q_due_soon_count.py"
    assert "--scope" in args
    assert "--days" in args
    assert args[args.index("--days") + 1] == "3"


def test_run_all_summary(repo):
    _, repository = repo
    message = repository.execute("all")
    assert "Query test summary" in message
    assert "`burndown`" in message
    assert "`due_soon`" in message


def test_run_command_prefix(repo):
    recorder, repository = repo
    repository.execute("run burndown")
    kind, script_name, args = recorder.calls[-1]
    assert kind == "args"
    assert script_name == "jira_q_burndown.py"