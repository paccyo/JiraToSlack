"""Deprecated stub for ``env_loader``.

This module previously contained environment-loading helpers. It now intentionally raises
an :class:`ImportError` so that any lingering imports fail fast with a clear message.
All callers must switch to :mod:`prototype.local_cli.lib.dotenv_loader` instead.
"""

raise ImportError(
    "env_loader has been removed. Please import from prototype.local_cli.lib.dotenv_loader instead."
)
