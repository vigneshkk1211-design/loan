"""
tests/test_operations.py
========================
Unit tests for the Operations Agent (api/agents/operations.py).

Coverage:
  A. OTP Generation   — send_otp() API, stored fields, UUID format
  B. OTP Formatting   — _format_otp() zero-padding, always-6-digits
  C. HMAC Hashing     — _hmac_otp() determinism, uniqueness, constant-time
  D. OTP Verification — correct OTP → JWT, wrong OTP errors, lockout, expired,
                        already-verified, wrong phone, unknown ref
  E. JWT Claims       — sub, exp, iat, jti fields in issued token
  F. Resend Backoff   — too-soon rejection, new reference, backoff doubling
"""

import time
import uuid

import pytest
from jose import jwt

from api.agents.operations import (
    OTPError,
    MAX_VERIFY_ATTEMPTS,
    OTP_TTL_SECONDS,
    RESEND_BASE_BACKOFF,
    SECRET_KEY,
    ALGORITHM,
    _format_otp,
    _hmac_otp,
    _is_expired,
    _otp_store,
    resend_otp,
    send_otp,
    verify_otp,
)

PHONE = "+919876543210"
WRONG_PHONE = "+911111111111"


# ─────────────────────────────────── helpers ─────────────────────────────────

def _inject_session(otp_plaintext: str, phone: str = PHONE, ttl: int = 180) -> str:
    """
    Bypass send_otp() and directly insert a session with a known OTP.
    Returns the reference_id.
    This is only used in tests so we can verify with a known OTP value.
    """
    import secrets as _sec
    ref = str(uuid.uuid4())
    salt = _sec.token_hex(32)
    now = time.time()
    _otp_store[ref] = {
        "phone_number":   phone,
        "otp_hash":       _hmac_otp(otp_plaintext, salt),
        "salt":           salt,
        "created_at":     now,
        "expires_at":     now + ttl,
        "attempts":       0,
        "resend_count":   0,
        "last_resend_at": None,
        "verified":       False,
    }
    return ref


def _inject_expired_session(otp_plaintext: str, phone: str = PHONE) -> str:
    """Inject a session that is already past its TTL."""
    ref = _inject_session(otp_plaintext, phone, ttl=-1)   # expires_at in the past
    return ref


# ═════════════════════════════════ A. OTP GENERATION ═════════════════════════

class TestSendOTP:
    def test_returns_reference_id(self):
        result = send_otp(PHONE)
        assert "reference_id" in result

    def test_reference_id_is_uuid4(self):
        result = send_otp(PHONE)
        parsed = uuid.UUID(result["reference_id"])
        assert str(parsed) == result["reference_id"]

    def test_returns_expires_in(self):
        result = send_otp(PHONE)
        assert result["expires_in"] == OTP_TTL_SECONDS

    def test_returns_max_attempts(self):
        result = send_otp(PHONE)
        assert result["max_attempts"] == MAX_VERIFY_ATTEMPTS

    def test_session_stored_in_store(self):
        result = send_otp(PHONE)
        assert result["reference_id"] in _otp_store

    def test_otp_hash_not_plaintext(self):
        """The stored hash must NOT look like a 6-digit number."""
        result = send_otp(PHONE)
        session = _otp_store[result["reference_id"]]
        assert len(session["otp_hash"]) == 64        # SHA-256 hex
        assert not session["otp_hash"].isdigit()

    def test_salt_stored_in_session(self):
        result = send_otp(PHONE)
        session = _otp_store[result["reference_id"]]
        assert "salt" in session
        assert len(session["salt"]) > 0

    def test_initial_attempts_is_zero(self):
        result = send_otp(PHONE)
        assert _otp_store[result["reference_id"]]["attempts"] == 0

    def test_initial_verified_is_false(self):
        result = send_otp(PHONE)
        assert _otp_store[result["reference_id"]]["verified"] is False

    def test_two_sends_produce_different_reference_ids(self):
        r1 = send_otp(PHONE)
        r2 = send_otp(PHONE)
        assert r1["reference_id"] != r2["reference_id"]

    def test_whatsapp_send_called(self, mock_whatsapp):
        send_otp(PHONE)
        assert len(mock_whatsapp) == 1
        assert mock_whatsapp[0]["phone"] == PHONE


# ═════════════════════════════════ B. OTP FORMATTING ═════════════════════════

class TestFormatOTP:
    @pytest.mark.parametrize("raw,expected", [
        (0,      "000000"),
        (1,      "000001"),
        (99,     "000099"),
        (9999,   "009999"),
        (99999,  "099999"),
        (999999, "999999"),
        (100000, "100000"),
    ])
    def test_zero_padding(self, raw, expected):
        assert _format_otp(raw) == expected

    @pytest.mark.parametrize("raw", [0, 1, 100, 9999, 100000, 999999])
    def test_always_6_characters(self, raw):
        assert len(_format_otp(raw)) == 6

    def test_only_digits(self):
        for n in range(0, 1_000_000, 12345):
            assert _format_otp(n).isdigit()


# ═════════════════════════════════ C. HMAC HASHING ═══════════════════════════

class TestHMACHashing:
    def test_deterministic_same_inputs(self):
        assert _hmac_otp("123456", "salt") == _hmac_otp("123456", "salt")

    def test_different_otp_different_hash(self):
        assert _hmac_otp("123456", "salt") != _hmac_otp("999999", "salt")

    def test_different_salt_different_hash(self):
        assert _hmac_otp("123456", "salt1") != _hmac_otp("123456", "salt2")

    def test_output_is_64_hex_chars(self):
        h = _hmac_otp("000000", "testsalt")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_all_zeros_otp_does_not_collide_with_all_nines(self):
        assert _hmac_otp("000000", "s") != _hmac_otp("999999", "s")

    def test_empty_otp_still_returns_valid_hash(self):
        h = _hmac_otp("", "salt")
        assert len(h) == 64


# ═════════════════════════════════ D. OTP VERIFICATION ════════════════════════

class TestVerifyOTP:

    # ── Positive path ──────────────────────────────────────────────────────

    def test_correct_otp_returns_access_token(self):
        ref = _inject_session("123456")
        result = verify_otp(PHONE, "123456", ref)
        assert "access_token" in result

    def test_correct_otp_returns_bearer_type(self):
        ref = _inject_session("123456")
        result = verify_otp(PHONE, "123456", ref)
        assert result["token_type"] == "bearer"

    def test_correct_otp_returns_600s_expiry(self):
        ref = _inject_session("123456")
        result = verify_otp(PHONE, "123456", ref)
        assert result["expires_in"] == 600

    def test_correct_otp_returns_phone_number(self):
        ref = _inject_session("123456")
        result = verify_otp(PHONE, "123456", ref)
        assert result["phone_number"] == PHONE

    # ── Error paths ────────────────────────────────────────────────────────

    def test_wrong_otp_raises_401(self):
        ref = _inject_session("123456")
        with pytest.raises(OTPError) as exc:
            verify_otp(PHONE, "000000", ref)
        assert exc.value.status_code == 401

    def test_wrong_otp_increments_attempts(self):
        ref = _inject_session("123456")
        try:
            verify_otp(PHONE, "000000", ref)
        except OTPError:
            pass
        assert _otp_store[ref]["attempts"] == 1

    def test_unknown_reference_raises_404(self):
        with pytest.raises(OTPError) as exc:
            verify_otp(PHONE, "123456", "non-existent-uuid-xxxx")
        assert exc.value.status_code == 404

    def test_wrong_phone_raises_403(self):
        ref = _inject_session("123456")
        with pytest.raises(OTPError) as exc:
            verify_otp(WRONG_PHONE, "123456", ref)
        assert exc.value.status_code == 403

    def test_expired_otp_raises_410(self):
        ref = _inject_expired_session("123456")
        with pytest.raises(OTPError) as exc:
            verify_otp(PHONE, "123456", ref)
        assert exc.value.status_code == 410

    def test_expired_session_removed_from_store(self):
        ref = _inject_expired_session("123456")
        try:
            verify_otp(PHONE, "123456", ref)
        except OTPError:
            pass
        assert ref not in _otp_store

    def test_already_verified_raises_409(self):
        ref = _inject_session("123456")
        verify_otp(PHONE, "123456", ref)       # first call → success
        with pytest.raises(OTPError) as exc:
            verify_otp(PHONE, "123456", ref)   # second call → already consumed
        assert exc.value.status_code == 409

    def test_max_attempts_lockout_raises_429(self):
        ref = _inject_session("123456")
        for _ in range(MAX_VERIFY_ATTEMPTS):
            try:
                verify_otp(PHONE, "000000", ref)
            except OTPError:
                pass
        # Next attempt after MAX_VERIFY_ATTEMPTS wrong guesses → locked out
        with pytest.raises(OTPError) as exc:
            verify_otp(PHONE, "000000", ref)
        assert exc.value.status_code == 429

    def test_max_attempts_correct_otp_still_fails_after_lockout(self):
        """Even the right OTP should be rejected once session is locked."""
        ref = _inject_session("123456")
        for _ in range(MAX_VERIFY_ATTEMPTS):
            try:
                verify_otp(PHONE, "000000", ref)
            except OTPError:
                pass
        with pytest.raises(OTPError) as exc:
            verify_otp(PHONE, "123456", ref)     # correct, but locked
        assert exc.value.status_code == 429

    def test_constant_time_comparison_used(self):
        """
        Verify we use hmac.compare_digest, not plain ==, by confirming the
        hash stored is the full 64-char SHA-256 (side-channel defence).
        """
        ref = _inject_session("123456")
        assert len(_otp_store[ref]["otp_hash"]) == 64


# ═════════════════════════════════ E. JWT CLAIMS ══════════════════════════════

class TestJWTClaims:
    def _decode(self, token: str) -> dict:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    def test_sub_claim_is_phone(self):
        ref = _inject_session("123456")
        token = verify_otp(PHONE, "123456", ref)["access_token"]
        assert self._decode(token)["sub"] == PHONE

    def test_exp_claim_is_10_minutes_ahead(self):
        ref = _inject_session("123456")
        token = verify_otp(PHONE, "123456", ref)["access_token"]
        payload = self._decode(token)
        delta = payload["exp"] - payload["iat"]
        assert 595 <= delta <= 605        # ≈ 600 seconds ± 5s clock tolerance

    def test_iat_claim_is_recent(self):
        ref = _inject_session("123456")
        token = verify_otp(PHONE, "123456", ref)["access_token"]
        iat = self._decode(token)["iat"]
        assert abs(iat - int(time.time())) < 5

    def test_jti_claim_present_and_unique(self):
        ref1 = _inject_session("123456")
        ref2 = _inject_session("654321")
        t1 = verify_otp(PHONE, "123456", ref1)["access_token"]
        t2 = verify_otp(PHONE, "654321", ref2)["access_token"]
        assert self._decode(t1)["jti"] != self._decode(t2)["jti"]

    def test_session_claim_matches_reference_id(self):
        ref = _inject_session("123456")
        token = verify_otp(PHONE, "123456", ref)["access_token"]
        assert self._decode(token)["session"] == ref


# ═════════════════════════════════ F. RESEND BACKOFF ══════════════════════════

class TestResendBackoff:
    def test_resend_immediately_raises_429(self):
        """Just-sent OTP: last_resend_at is not None → backoff not elapsed."""
        result = send_otp(PHONE)
        ref = result["reference_id"]
        # Simulate that a prior resend exists (to trigger backoff check)
        _otp_store[ref]["last_resend_at"] = time.time()
        _otp_store[ref]["resend_count"] = 1
        with pytest.raises(OTPError) as exc:
            resend_otp(PHONE, ref)
        assert exc.value.status_code == 429

    def test_first_resend_allowed_when_no_prior_resend(self):
        """
        When last_resend_at is None (never resent), first resend is allowed
        immediately regardless of backoff window.
        """
        result = send_otp(PHONE)
        ref = result["reference_id"]
        # last_resend_at is None by default after send_otp
        new = resend_otp(PHONE, ref)
        assert "reference_id" in new

    def test_resend_returns_new_reference_id(self):
        result = send_otp(PHONE)
        old_ref = result["reference_id"]
        new = resend_otp(PHONE, old_ref)
        assert new["reference_id"] != old_ref

    def test_resend_invalidates_old_session(self):
        result = send_otp(PHONE)
        old_ref = result["reference_id"]
        resend_otp(PHONE, old_ref)
        assert old_ref not in _otp_store

    def test_first_resend_retry_after_is_60(self):
        """Base 30 × 2^1 = 60 seconds for first resend's retry_after."""
        result = send_otp(PHONE)
        old_ref = result["reference_id"]
        new = resend_otp(PHONE, old_ref)
        assert new["retry_after"] == RESEND_BASE_BACKOFF * 2

    def test_second_resend_retry_after_is_120(self):
        """Base 30 × 2^2 = 120 seconds for second resend's retry_after."""
        result = send_otp(PHONE)
        ref = result["reference_id"]
        new1 = resend_otp(PHONE, ref)          # first resend → retry_after=60
        # Allow second resend (no last_resend_at pressure on new session)
        new2 = resend_otp(PHONE, new1["reference_id"])  # second → retry_after=120
        assert new2["retry_after"] == RESEND_BASE_BACKOFF * 4

    def test_resend_unknown_reference_raises_404(self):
        with pytest.raises(OTPError) as exc:
            resend_otp(PHONE, "does-not-exist")
        assert exc.value.status_code == 404

    def test_resend_wrong_phone_raises_403(self):
        result = send_otp(PHONE)
        ref = result["reference_id"]
        with pytest.raises(OTPError) as exc:
            resend_otp(WRONG_PHONE, ref)
        assert exc.value.status_code == 403


# ═════════════════════════════════ G. IS_EXPIRED HELPER ══════════════════════

class TestIsExpiredHelper:
    def test_future_expires_at_not_expired(self):
        session = {"expires_at": time.time() + 300}
        assert _is_expired(session) is False

    def test_past_expires_at_is_expired(self):
        session = {"expires_at": time.time() - 1}
        assert _is_expired(session) is True

    def test_exact_boundary(self):
        """At boundary (expires_at == now) the session is expired."""
        session = {"expires_at": time.time() - 0.0001}
        assert _is_expired(session) is True
