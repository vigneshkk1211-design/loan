"""
conftest.py — Root-level pytest configuration
=============================================
Sets required environment variables BEFORE any agent module is imported,
so that SECRET_KEY and AUDIT_LOG_PATH are already in os.environ when the
top-level module-scope assignments run in operations.py / compliance.py.

Fixtures defined here are available to ALL test modules automatically.
"""

import os
import tempfile

import pytest

# ── Set env vars BEFORE any agent module imports ─────────────────────────────
# Must happen at module scope (not inside a fixture) so that:
#   SECRET_KEY: str = os.environ.get("SECRET_KEY", "DEV_ONLY...")   ← operations.py
# picks up the test value when the module is first imported.
os.environ.setdefault("SECRET_KEY", "TEST_SECRET_KEY_FOR_PYTEST_32CHARS_X")

# Redirect the audit log to a temp file so tests don't pollute /tmp or CWD.
_TEMP_AUDIT_LOG = tempfile.NamedTemporaryFile(
    prefix="finflow_test_audit_", suffix=".log", delete=False
)
_TEMP_AUDIT_LOG.close()
os.environ["AUDIT_LOG_PATH"] = _TEMP_AUDIT_LOG.name


# ── Per-test OTP store cleanup ────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def clear_otp_store():
    """
    Wipe the in-memory OTP session store before and after every test.
    Prevents state leaking between tests when the module-global _otp_store
    accumulates sessions across test functions.
    """
    from api.agents.operations import _otp_store
    _otp_store.clear()
    yield
    _otp_store.clear()


# ── Per-test delivery store cleanup ──────────────────────────────────────────
@pytest.fixture(autouse=True)
def clear_delivery_store():
    """
    Wipe the in-memory KFS delivery store before and after every test.
    Prevents delivery-state leaking between compliance test cases.
    """
    from api.agents.compliance import _delivery_store
    _delivery_store.clear()
    yield
    _delivery_store.clear()


# ── Suppress real WhatsApp delivery ──────────────────────────────────────────
@pytest.fixture(autouse=True)
def mock_whatsapp(monkeypatch):
    """
    Replace _send_whatsapp_otp with a no-op so tests never make external
    HTTP calls to Twilio / Meta Cloud API.
    Captured calls are available via the `whatsapp_calls` list if needed.
    """
    calls = []

    def fake_send(phone: str, otp: str) -> None:
        calls.append({"phone": phone, "otp": otp})

    monkeypatch.setattr("api.agents.operations._send_whatsapp_otp", fake_send)
    return calls
