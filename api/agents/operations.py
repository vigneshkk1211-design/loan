"""
Operations Agent — WhatsApp OTP Workflow
=========================================
Implements secure 6-digit OTP generation, verification, and resend with:

  • secrets.randbelow(1_000_000) — cryptographically random 6-digit OTP
  • Salted HMAC-SHA256 hash storage  — OTP plaintext never persisted
  • 3-minute TTL per OTP session
  • Max 3 verify attempts before session lockout
  • Exponential backoff for resend (base 30 s, doubles each attempt)
  • Short-lived JWT (10-min) issued on successful verify via python-jose

⚠️  Storage note: OTP sessions are stored in-memory (_otp_store dict).
    On Vercel serverless, this dict is ephemeral and does NOT persist
    across function cold-starts. Replace with Redis or a DB in production.

⚠️  WhatsApp delivery: _send_whatsapp_otp() is a placeholder hook.
    Wire in Twilio / Meta Cloud API credentials to deliver real messages.
"""

import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from typing import Any, Dict

from jose import jwt

# ── Configuration ────────────────────────────────────────────────────────────

SECRET_KEY: str = os.environ.get("SECRET_KEY", "DEV_ONLY_CHANGE_IN_PRODUCTION_SECRET")
ALGORITHM: str = "HS256"

OTP_TTL_SECONDS: int = 180          # 3 minutes
JWT_TTL_SECONDS: int = 600          # 10 minutes
MAX_VERIFY_ATTEMPTS: int = 3
RESEND_BASE_BACKOFF: int = 30       # seconds (doubles each resend)

# In-memory session store.  Replace with Redis in production.
# Schema: { reference_id: SessionRecord }
_otp_store: Dict[str, Dict[str, Any]] = {}


# ── Internal helpers ─────────────────────────────────────────────────────────

def _generate_salt() -> str:
    """Return a 32-byte hex random salt."""
    return secrets.token_hex(32)


def _hmac_otp(otp: str, salt: str) -> str:
    """
    Compute HMAC-SHA256(key=SECRET_KEY, msg=salt+otp).

    The salt is concatenated with the OTP before hashing so that even if
    two users coincidentally receive the same OTP at the same time, their
    stored hashes differ.
    """
    msg = (salt + otp).encode("utf-8")
    key = SECRET_KEY.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _send_whatsapp_otp(phone_number: str, otp: str) -> None:
    """
    🔌 Placeholder — wire up Twilio/Meta Cloud API here.

    Example (Twilio):
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(
            from_="whatsapp:+14155238886",
            to=f"whatsapp:{phone_number}",
            body=f"Your OTP is {otp}. Valid for 3 minutes. Do not share.",
        )
    """
    # For development: print to console
    print(f"[OTP] Would send '{otp}' to {phone_number} via WhatsApp")


def _format_otp(raw: int) -> str:
    """Zero-pad the OTP integer to exactly 6 digits."""
    return f"{raw:06d}"


def _is_expired(session: Dict[str, Any]) -> bool:
    return time.time() > session["expires_at"]


def _purge_expired() -> None:
    """Lazily remove expired sessions to keep memory bounded."""
    now = time.time()
    expired = [k for k, v in _otp_store.items() if now > v["expires_at"]]
    for k in expired:
        del _otp_store[k]


# ── Public API ───────────────────────────────────────────────────────────────

class OTPError(Exception):
    """Raised for business-rule violations (wrong OTP, expired, rate-limited)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def send_otp(phone_number: str) -> Dict[str, Any]:
    """
    Generate a cryptographically random 6-digit OTP and persist its hash.

    Args:
        phone_number: E.164 phone number string.

    Returns:
        dict with reference_id, expires_in, message.
    """
    _purge_expired()

    # Generate OTP
    raw_otp = secrets.randbelow(1_000_000)
    otp_str = _format_otp(raw_otp)

    # Salted HMAC storage
    salt = _generate_salt()
    otp_hash = _hmac_otp(otp_str, salt)

    reference_id = str(uuid.uuid4())
    session: Dict[str, Any] = {
        "phone_number": phone_number,
        "otp_hash": otp_hash,
        "salt": salt,
        "created_at": time.time(),
        "expires_at": time.time() + OTP_TTL_SECONDS,
        "attempts": 0,
        "resend_count": 0,
        "last_resend_at": None,
        "verified": False,
    }
    _otp_store[reference_id] = session

    # Deliver via WhatsApp (placeholder)
    _send_whatsapp_otp(phone_number, otp_str)

    return {
        "message": f"OTP sent to {phone_number} via WhatsApp",
        "reference_id": reference_id,
        "expires_in": OTP_TTL_SECONDS,
        "max_attempts": MAX_VERIFY_ATTEMPTS,
    }


def verify_otp(phone_number: str, otp: str, reference_id: str) -> Dict[str, Any]:
    """
    Verify the OTP against the stored HMAC hash.

    Args:
        phone_number:  Must match the phone number used during send.
        otp:           6-digit string provided by the user.
        reference_id:  Session ID returned by send_otp().

    Returns:
        dict with access_token, token_type, expires_in, phone_number.

    Raises:
        OTPError: On any verification failure (expired, wrong OTP, max attempts).
    """
    session = _otp_store.get(reference_id)

    if session is None:
        raise OTPError("Invalid or unknown reference_id", status_code=404)

    if session["phone_number"] != phone_number:
        raise OTPError("phone_number does not match OTP session", status_code=403)

    if session["verified"]:
        raise OTPError("OTP already consumed; request a new one", status_code=409)

    if _is_expired(session):
        del _otp_store[reference_id]
        raise OTPError("OTP has expired; please request a new one", status_code=410)

    if session["attempts"] >= MAX_VERIFY_ATTEMPTS:
        raise OTPError(
            f"Maximum {MAX_VERIFY_ATTEMPTS} attempts exceeded; session locked",
            status_code=429,
        )

    # Constant-time HMAC comparison — re-derive hash from user input and
    # compare against the stored hash using compare_digest to prevent
    # timing side-channel attacks.
    candidate_hash = _hmac_otp(otp, session["salt"])
    if not hmac.compare_digest(session["otp_hash"], candidate_hash):
        session["attempts"] += 1
        remaining = MAX_VERIFY_ATTEMPTS - session["attempts"]
        raise OTPError(
            f"Incorrect OTP. {remaining} attempt(s) remaining",
            status_code=401,
        )

    # Mark session as consumed
    session["verified"] = True

    # Issue JWT
    now = int(time.time())
    payload = {
        "sub": phone_number,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
        "jti": str(uuid.uuid4()),
        "session": reference_id,
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_TTL_SECONDS,
        "phone_number": phone_number,
    }


def resend_otp(phone_number: str, reference_id: str) -> Dict[str, Any]:
    """
    Resend OTP with exponential backoff rate limiting.

    Backoff schedule (seconds): 30, 60, 120, 240, … (base × 2^resend_count)

    Args:
        phone_number:  E.164 phone number.
        reference_id:  Original session reference_id.

    Returns:
        dict with new reference_id, retry_after, expires_in, message.

    Raises:
        OTPError: If backoff window has not elapsed.
    """
    session = _otp_store.get(reference_id)

    if session is None:
        raise OTPError("Invalid or unknown reference_id", status_code=404)

    if session["phone_number"] != phone_number:
        raise OTPError("phone_number does not match OTP session", status_code=403)

    # Enforce exponential backoff
    resend_count: int = session["resend_count"]
    backoff_seconds: int = RESEND_BASE_BACKOFF * (2 ** resend_count)
    last_resend: float | None = session["last_resend_at"]

    if last_resend is not None:
        elapsed = time.time() - last_resend
        if elapsed < backoff_seconds:
            wait = int(backoff_seconds - elapsed)
            raise OTPError(
                f"Rate limited. Retry after {wait} seconds",
                status_code=429,
            )

    # Invalidate old session and create a fresh one
    del _otp_store[reference_id]

    result = send_otp(phone_number)
    new_ref = result["reference_id"]

    # Carry over resend metadata to new session
    new_session = _otp_store[new_ref]
    new_session["resend_count"] = resend_count + 1
    new_session["last_resend_at"] = time.time()

    next_backoff = RESEND_BASE_BACKOFF * (2 ** (resend_count + 1))

    return {
        "message": f"OTP resent to {phone_number} via WhatsApp",
        "reference_id": new_ref,
        "retry_after": next_backoff,
        "expires_in": OTP_TTL_SECONDS,
    }
