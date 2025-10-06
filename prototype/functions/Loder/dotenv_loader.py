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
    """Load environment variables from candidate .env files unless running tests.

    ポイント:
    - pytest 実行中は `.env` を読まない (テストが意図せず本番認証を拾うのを防止)
    - 明示的な専用フラグ環境変数は追加しない (要望: 余計な環境変数導入を避ける)
    判定ロジック:
      * 環境変数 PYTEST_CURRENT_TEST が存在
        もしくは sys.argv[0] / コマンドラインに 'pytest' が含まれる
    """
    import sys

    # Detect pytest without introducing a new env toggle
    running_pytest = (
        'PYTEST_CURRENT_TEST' in os.environ or
        any('pytest' in (arg or '') for arg in sys.argv[:2])
    )
    if running_pytest:
        # Skip loading .env files to keep tests deterministic
        return False

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
