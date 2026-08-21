"""
Router: WhatsApp OTP Authentication
Routes:
  POST /api/v1/otp/send    — Generate & send OTP
  POST /api/v1/otp/verify  — Verify OTP, issue JWT
  POST /api/v1/otp/resend  — Resend with exponential backoff

Delegates to the Operations Agent for all OTP business logic.
"""

from fastapi import APIRouter, HTTPException, status

from api.agents.operations import OTPError, send_otp, verify_otp, resend_otp
from api.models.otp import (
    OTPResendRequest,
    OTPResendResponse,
    OTPSendRequest,
    OTPSendResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
)

router = APIRouter(
    prefix="/otp",
    tags=["Operations Agent — WhatsApp OTP"],
)


def _otp_error_to_http(exc: OTPError) -> HTTPException:
    """Map an OTPError business exception to the appropriate HTTP status."""
    return HTTPException(status_code=exc.status_code, detail=str(exc))


# ── POST /api/v1/otp/send ────────────────────────────────────────────────────

@router.post(
    "/send",
    response_model=OTPSendResponse,
    status_code=status.HTTP_200_OK,
    summary="Send WhatsApp OTP",
    description="""
Generate a cryptographically secure 6-digit OTP and deliver it to the
borrower's WhatsApp number.

**Security details:**
- OTP generated with `secrets.randbelow(1_000_000)` (CSPRNG)
- Stored as salted **HMAC-SHA256** hash — plaintext never persisted
- Valid for **3 minutes** (180 seconds)
- Maximum **3 verify attempts** before session lockout

Returns a `reference_id` (UUID4) that must be passed to `/otp/verify`
and `/otp/resend`.
""",
    responses={
        200: {"description": "OTP sent successfully"},
        422: {"description": "Invalid phone number format"},
    },
)
async def send(body: OTPSendRequest) -> OTPSendResponse:
    """
    - **phone_number**: Recipient in E.164 format (e.g. `+919876543210`)
    """
    try:
        result = send_otp(body.phone_number)
        return OTPSendResponse(**result)
    except OTPError as exc:
        raise _otp_error_to_http(exc) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OTP send failed: {exc}",
        ) from exc


# ── POST /api/v1/otp/verify ──────────────────────────────────────────────────

@router.post(
    "/verify",
    response_model=OTPVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify OTP & Issue JWT",
    description="""
Verify the 6-digit OTP against the stored HMAC-SHA256 hash.

On success, issues a **short-lived JWT** (10 minutes / 600 seconds)
signed with HMAC-SHA256 (`HS256`). The token's `sub` claim contains the
verified phone number.

**Failure modes:**
| Condition | HTTP Code |
|-----------|-----------|
| Unknown reference_id | 404 |
| Wrong phone number | 403 |
| OTP expired | 410 |
| Wrong OTP (with remaining attempts) | 401 |
| Max attempts exceeded | 429 |
| Already consumed session | 409 |
""",
    responses={
        200: {"description": "OTP verified; JWT issued"},
        401: {"description": "Incorrect OTP"},
        403: {"description": "Phone number mismatch"},
        404: {"description": "Unknown reference_id"},
        409: {"description": "OTP session already consumed"},
        410: {"description": "OTP expired"},
        429: {"description": "Max attempts exceeded"},
    },
)
async def verify(body: OTPVerifyRequest) -> OTPVerifyResponse:
    """
    - **phone_number**: Must match the number used in `/otp/send`
    - **otp**: 6-digit code received on WhatsApp
    - **reference_id**: UUID4 from the `/otp/send` response
    """
    try:
        result = verify_otp(body.phone_number, body.otp, body.reference_id)
        return OTPVerifyResponse(**result)
    except OTPError as exc:
        raise _otp_error_to_http(exc) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OTP verify failed: {exc}",
        ) from exc


# ── POST /api/v1/otp/resend ──────────────────────────────────────────────────

@router.post(
    "/resend",
    response_model=OTPResendResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend OTP (Exponential Backoff)",
    description="""
Resend the OTP to the same phone number with **exponential backoff**
rate limiting to prevent abuse.

**Backoff schedule** (seconds between allowed resends):

| Resend # | Wait Before Allowed |
|----------|---------------------|
| 1st      | 30 s                |
| 2nd      | 60 s                |
| 3rd      | 120 s               |
| 4th      | 240 s               |
| n-th     | 30 × 2^(n-1) s      |

A new `reference_id` is returned; the old session is invalidated.
""",
    responses={
        200: {"description": "OTP resent successfully"},
        404: {"description": "Unknown reference_id"},
        403: {"description": "Phone number mismatch"},
        429: {"description": "Rate limited; retry_after header indicates wait time"},
    },
)
async def resend(body: OTPResendRequest) -> OTPResendResponse:
    """
    - **phone_number**: E.164 phone number (must match original send)
    - **reference_id**: UUID4 from the previous `/otp/send` or `/otp/resend`
    """
    try:
        result = resend_otp(body.phone_number, body.reference_id)
        return OTPResendResponse(**result)
    except OTPError as exc:
        raise _otp_error_to_http(exc) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OTP resend failed: {exc}",
        ) from exc
