"""Utilities for loading environment variables using python-dotenv."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Optional

from dotenv import load_dotenv


def _candidate_paths() -> Iterable[Path]:
    """Return candidate .env files in priority order."""
    lib_dir = Path(__file__).resolve().parent
    local_cli_dir = lib_dir.parent
    repo_root = local_cli_dir.parent
    cwd = Path.cwd()
    return (
        local_cli_dir / ".env",
        local_cli_dir / "queries" / ".env",
        cwd / ".env",
        repo_root / ".env",
    )


@lru_cache(maxsize=1)
def ensure_env_loaded(override: bool = True) -> bool:
    """Load environment variables from candidate .env files.

    Returns True if at least one .env file was loaded.
    """
    loaded = False
    for path in _candidate_paths():
        if path.exists():
            load_dotenv(path, override=override)
            loaded = True
    return loaded


def build_process_env(extra: Optional[Dict[str, Optional[str]]] = None) -> Dict[str, str]:
    """Return os.environ copy with .env values applied."""
    ensure_env_loaded(override=True)
    env = os.environ.copy()
    if extra:
        env.update({k: v for k, v in extra.items() if v is not None})
    return env
