from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from prototype.local_cli.Loder.dotenv_loader import ensure_env_loaded


@dataclass(frozen=True)
class QueryDefinition:
    key: str
    script: Path
    description: str
    args_builder: Optional[Callable[["CommandJiraRepository"], List[str]]] = None


class CommandJiraRepository:
    """Run Jira data queries used by the dashboard and return Slack-friendly text."""

    def __init__(
        self,
        get_json: Optional[Callable[[str, Optional[Dict[str, str]]], Dict[str, Any]]] = None,
        get_json_with_args: Optional[
            Callable[[str, List[str], Optional[Dict[str, str]]], Dict[str, Any]]
        ] = None,
        max_chars: int = 1800,
    ) -> None:
        module = None
        if get_json is None or get_json_with_args is None:
            module = importlib.import_module("prototype.local_cli.main")
        ensure_env_loaded()
        self._repo_root = Path(__file__).resolve().parents[2]
        self._queries_dir = self._repo_root / "prototype" / "local_cli" / "queries"
        self._get_json = get_json or getattr(module, "get_json_from_script")
        self._get_json_args = get_json_with_args or getattr(module, "get_json_from_script_args")
        self._max_chars = max(400, max_chars)
        self._definitions = self._build_definitions()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def execute(self, text: Optional[str]) -> str:
        tokens = (text or "").strip().split()
        if not tokens:
            return self._build_help_message()

        head = tokens[0].lower()
        if head in {"help", "list"}:
            return self._build_help_message()

        if head == "run":
            if len(tokens) < 2:
                return "`/jira run <query>` の形式でクエリ名を指定してください。"
            alias = tokens[1].lower()
        else:
            alias = head

        if alias == "all":
            return self._run_all()

        if alias not in self._definitions:
            return self._unknown_alias_message(alias)

        return self._run_single(alias)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_definitions(self) -> Dict[str, QueryDefinition]:
        def script(name: str) -> Path:
            return (self._queries_dir / name).resolve()

        def burndown_args(_: "CommandJiraRepository") -> List[str]:
            unit = os.getenv("BURNDOWN_UNIT", "issues")
            return ["--unit", unit]

        def velocity_args(_: "CommandJiraRepository") -> List[str]:
            n_sprints = os.getenv("N_SPRINTS", "6").strip()
            return ["--n", n_sprints] if n_sprints else []

        def status_counts_args(_: "CommandJiraRepository") -> List[str]:
            mode = os.getenv("STATUS_COUNTS_MODE", "approx")
            return ["--scope", "sprint", "--mode", mode]

        def time_in_status_args(_: "CommandJiraRepository") -> List[str]:
            unit = os.getenv("TIS_UNIT", "days")
            return ["--scope", "sprint", "--unit", unit]

        def workload_args(_: "CommandJiraRepository") -> List[str]:
            return ["--scope", "sprint"]

        def overdue_args(_: "CommandJiraRepository") -> List[str]:
            return ["--scope", "sprint"]

        def due_soon_args(repo: "CommandJiraRepository") -> List[str]:
            return ["--scope", "sprint", "--days", str(repo._get_due_soon_days())]

        def unassigned_args(_: "CommandJiraRepository") -> List[str]:
            return ["--scope", "sprint"]

        return {
            "subtasks": QueryDefinition(
                key="subtasks",
                script=script("jira_list_sprint_subtasks.py"),
                description="アクティブスプリントの親子タスク一覧",
            ),
            "burndown": QueryDefinition(
                key="burndown",
                script=script("jira_q_burndown.py"),
                description="バーンダウンデータ",
                args_builder=burndown_args,
            ),
            "velocity": QueryDefinition(
                key="velocity",
                script=script("jira_q_velocity_history.py"),
                description="ベロシティ履歴",
                args_builder=velocity_args,
            ),
            "project_sprint_count": QueryDefinition(
                key="project_sprint_count",
                script=script("jira_count_project_sprints.py"),
                description="プロジェクト全体のスプリント数",
                args_builder=lambda _: [],
            ),
            "status_counts": QueryDefinition(
                key="status_counts",
                script=script("jira_q_status_counts.py"),
                description="ステータス分布 (スプリント)",
                args_builder=status_counts_args,
            ),
            "time_in_status": QueryDefinition(
                key="time_in_status",
                script=script("jira_q_time_in_status.py"),
                description="滞留時間集計",
                args_builder=time_in_status_args,
            ),
            "workload": QueryDefinition(
                key="workload",
                script=script("jira_q_assignee_workload.py"),
                description="担当者別ワークロード",
                args_builder=workload_args,
            ),
            "overdue": QueryDefinition(
                key="overdue",
                script=script("jira_q_overdue_count.py"),
                description="期限超過タスク数",
                args_builder=overdue_args,
            ),
            "due_soon": QueryDefinition(
                key="due_soon",
                script=script("jira_q_due_soon_count.py"),
                description="期限間近タスク数",
                args_builder=due_soon_args,
            ),
            "unassigned": QueryDefinition(
                key="unassigned",
                script=script("jira_q_unassigned_count.py"),
                description="未割り当てタスク数",
                args_builder=unassigned_args,
            ),
            "project_subtasks": QueryDefinition(
                key="project_subtasks",
                script=script("jira_count_project_subtasks.py"),
                description="プロジェクト全体のサブタスク数",
                args_builder=lambda _: [],
            ),
        }

    def _get_due_soon_days(self) -> int:
        raw = os.getenv("DUE_SOON_DAYS", "7").strip()
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 7

    def _run_single(self, alias: str) -> str:
        definition = self._definitions[alias]
        try:
            result = self._execute_definition(definition)
            formatted = self._format_json(result)
            return f"*Query `{alias}` result:*\n```{formatted}```"
        except Exception as exc:  # pragma: no cover - surfaced to Slack users
            return f":x: Query `{alias}` の実行に失敗しました: {exc}"

    def _run_all(self) -> str:
        lines = ["*Query test summary (all queries)*"]
        for alias, definition in self._definitions.items():
            try:
                result = self._execute_definition(definition)
                summary = self._summarize_result(result)
                lines.append(f"• `{alias}`: OK - {summary}")
            except Exception as exc:  # pragma: no cover - surfaced to Slack users
                lines.append(f"• `{alias}`: ERROR - {exc}")
        lines.append("\n個別の詳細は `/jira <query>` で確認できます。")
        return "\n".join(lines)

    def _execute_definition(self, definition: QueryDefinition) -> Any:
        script_path = str(definition.script)
        if not definition.script.exists():
            raise FileNotFoundError(f"スクリプトが見つかりません: {definition.script}")
        if definition.args_builder is None:
            return self._get_json(script_path)
        args = definition.args_builder(self)
        return self._get_json_args(script_path, args)

    def _format_json(self, payload: Any) -> str:
        try:
            text = json.dumps(payload, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            text = str(payload)
        if len(text) > self._max_chars:
            truncated = text[: self._max_chars].rstrip()
            return f"{truncated}\n... (出力を省略しました)"
        return text

    def _summarize_result(self, payload: Any) -> str:
        if isinstance(payload, dict):
            keys = list(payload.keys())
            if not keys:
                return "dict (keys=0)"
            preview = ", ".join(keys[:3])
            if len(keys) > 3:
                preview += f", … (+{len(keys) - 3})"
            return f"dict keys: {preview}"
        if isinstance(payload, list):
            return f"list length {len(payload)}"
        return f"type {type(payload).__name__}"

    def _build_help_message(self) -> str:
        lines = [
            "*Jira query data test*",
            "`/jira <query>` でダッシュボード用クエリを個別に実行し、結果をJSONで確認できます。",
            "例: `/jira burndown` / `/jira run status_counts` / `/jira all`",
            "",
            "*利用可能なクエリ:*",
        ]
        for alias, definition in self._definitions.items():
            lines.append(f"• `{alias}` — {definition.description} ({definition.script.name})")
        lines.append("\nヘルプ: `/jira help` または `/jira list`")
        return "\n".join(lines)

    def _unknown_alias_message(self, alias: str) -> str:
        suggestions = ", ".join(f"`{key}`" for key in self._definitions.keys())
        return f"`{alias}` は未対応のクエリです。利用可能なクエリ: {suggestions}"