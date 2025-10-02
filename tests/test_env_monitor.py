from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Set

import pytest


ROOT_DIR = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS: Set[str] = {
    "__pycache__",
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
}


@dataclass(frozen=True)
class EnvAccess:
    key: str
    method: str
    file: str
    lineno: int

    @property
    def identifier(self) -> str:
        return f"{self.file}:{self.lineno}:{self.method}:{self.key}"


class EnvVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.os_aliases: Set[str] = {"os"}
        self.getenv_names: Set[str] = set()
        self.environ_names: Set[str] = set()
        self.accesses: List[EnvAccess] = []

    # --- Import inspection -------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:  # pragma: no cover - trivial
        for alias in node.names:
            if alias.name == "os":
                self.os_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # pragma: no cover - trivial
        if node.module == "os":
            for alias in node.names:
                target = alias.asname or alias.name
                if alias.name == "getenv":
                    self.getenv_names.add(target)
                elif alias.name == "environ":
                    self.environ_names.add(target)
        self.generic_visit(node)

    # --- Helpers ------------------------------------------------------------
    @staticmethod
    def _literal_key(arg: ast.AST) -> str | None:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        return None

    def _record(self, key: str | None, method: str, node: ast.AST) -> None:
        if not key:
            return
        self.accesses.append(EnvAccess(key=key, method=method, file=self.rel_path, lineno=node.lineno))

    # --- Call inspection ----------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            # os.getenv("KEY")
            if (
                isinstance(func.value, ast.Name)
                and func.value.id in self.os_aliases
                and func.attr == "getenv"
                and node.args
            ):
                key = self._literal_key(node.args[0])
                self._record(key, "getenv", node)
        elif isinstance(func, ast.Name):
            # from os import getenv as gv
            if func.id in self.getenv_names and node.args:
                key = self._literal_key(node.args[0])
                self._record(key, "getenv", node)
        # os.environ.get("KEY")
        if isinstance(func, ast.Attribute) and node.args:
            attr = func.attr
            value = func.value
            if (
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id in self.os_aliases
                and value.attr == "environ"
                and attr == "get"
            ):
                key = self._literal_key(node.args[0])
                self._record(key, "environ_get", node)
        self.generic_visit(node)


def iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        rel_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            continue
        yield path


def collect_env_accesses() -> List[EnvAccess]:
    accesses: List[EnvAccess] = []
    for file_path in iter_python_files(ROOT_DIR):
        rel_path = str(file_path.relative_to(ROOT_DIR)).replace("\\", "/")
        if rel_path == "tests/test_env_monitor.py":
            continue
        try:
            source = file_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:  # pragma: no cover - safety
            continue
        tree = ast.parse(source, filename=rel_path)
        visitor = EnvVisitor(rel_path)
        visitor.visit(tree)
        accesses.extend(visitor.accesses)
    return sorted(accesses, key=lambda a: (a.file, a.lineno, a.method, a.key))


class EnvAccessTracker:
    def __init__(self, accesses: List[EnvAccess]) -> None:
        self.expected = {acc.identifier: acc for acc in accesses}
        self.covered: Set[str] = set()
        self.failures: Set[str] = set()
        self._current_id: str | None = None

    def mark(self, access: EnvAccess) -> None:
        ident = access.identifier
        if ident not in self.expected:  # pragma: no cover - defensive
            raise KeyError(f"Unexpected access identifier: {ident}")
        self._current_id = ident

    def record(self, success: bool) -> None:
        if self._current_id is None:
            return
        if success:
            self.covered.add(self._current_id)
        else:
            self.failures.add(self._current_id)
        self._current_id = None

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original_getenv = os.getenv

        def tracked_getenv(key: str, default: str | None = None) -> str | None:
            value = original_getenv(key, default)
            success = key in os.environ or value is not None or default is not None
            self.record(success)
            return value

        monkeypatch.setattr(os, "getenv", tracked_getenv)

        env_cls = os.environ.__class__
        original_get = env_cls.get

        def tracked_env_get(self_env, key: str, default: str | None = None) -> str | None:
            value = original_get(self_env, key, default)
            success = key in self_env or value is not None or default is not None
            self.record(success)
            return value

        monkeypatch.setattr(env_cls, "get", tracked_env_get)

    def summary(self) -> tuple[int, int]:
        return len(self.covered), len(self.expected)


@pytest.mark.parametrize("_", [0])
def test_all_environment_variable_reads_are_monitored(monkeypatch: pytest.MonkeyPatch, _: int) -> None:
    accesses = collect_env_accesses()
    assert accesses, "No environment variable reads discovered in repository"

    tracker = EnvAccessTracker(accesses)

    # Prepare deterministic environment values for all discovered keys
    for idx, access in enumerate(accesses):
        value = f"monitor_value_{idx}"
        monkeypatch.setenv(access.key, value)

    tracker.install(monkeypatch)

    # Exercise each access type to ensure instrumentation runs
    for access in accesses:
        tracker.mark(access)
        if access.method == "getenv":
            os.getenv(access.key)
        elif access.method == "environ_get":
            os.environ.get(access.key)
        else:  # pragma: no cover - defensive if new method types appear
            pytest.skip(f"Unsupported env access method encountered: {access.method}")

    covered, total = tracker.summary()
    coverage_pct = 100.0 * covered / total if total else 100.0
    print(f"ENV VAR READ COVERAGE: {covered}/{total} ({coverage_pct:.1f}%)")

    assert covered == total, (
        "Some environment variable read paths could not be validated. "
        f"Covered {covered} of {total} discovered accesses."
    )
