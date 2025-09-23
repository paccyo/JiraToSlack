import os
import pytest


def test_fmt_date_formats():
    from prototype.local_cli.main import fmt_date
    assert fmt_date("2025-09-01") == "2025/09/01"
    assert fmt_date("2025-09-01T12:34:56+0900").startswith("2025/09/01")
    assert fmt_date("2025-09-01T12:34:56Z").startswith("2025/09/01")
    assert fmt_date(None) is None


def test_maybe_gemini_summary_without_key(monkeypatch):
    # Ensure no API key
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from prototype.local_cli.main import maybe_gemini_summary
    out = maybe_gemini_summary(None, {"x": 1})
    assert out is None