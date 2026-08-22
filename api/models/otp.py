"""
Pydantic request/response models for the WhatsApp OTP endpoints.

Reference IDs are UUID4 strings that tie a send→verify→resend lifecycle.
"""

from pydantic import BaseModel, Field, field_validator
import re


_PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class OTPSendRequest(BaseModel):
    """Request body for POST /api/v1/otp/send."""

    phone_number: str = Field(
        ...,
        description="Recipient phone number in E.164 format (e.g. +919876543210)",
        examples=["+919876543210"],
    )

    @field_validator("phone_number")
    @classmethod
    def validate_e164(cls, v: str) -> str:
        if not _PHONE_RE.match(v):
            raise ValueError("phone_number must be in E.164 format, e.g. +919876543210")
        return v

    model_config = {
        "json_schema_extra": {"example": {"phone_number": "+919876543210"}}
    }


class OTPSendResponse(BaseModel):
    """Response body for POST /api/v1/otp/send."""

    message: str = Field(..., description="Human-readable status message")
    reference_id: str = Field(..., description="UUID4 reference for this OTP session")
    expires_in: int = Field(..., description="OTP validity in seconds (180 = 3 minutes)")
    max_attempts: int = Field(default=3, description="Maximum verify attempts allowed")
    demo_otp: str | None = Field(default=None, description="Plaintext OTP returned for testing convenience")



class OTPVerifyRequest(BaseModel):
    """Request body for POST /api/v1/otp/verify."""

    phone_number: str = Field(
        ...,
        description="Same phone number used during send",
        examples=["+919876543210"],
    )
    otp: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="6-digit OTP received on WhatsApp",
        examples=["482910"],
    )
    reference_id: str = Field(
        ...,
        description="reference_id returned by /otp/send",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )

    @field_validator("phone_number")
    @classmethod
    def validate_e164(cls, v: str) -> str:
        if not _PHONE_RE.match(v):
            raise ValueError("phone_number must be in E.164 format")
        return v

    @field_validator("otp")
    @classmethod
    def digits_only(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP must contain exactly 6 digits")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "phone_number": "+919876543210",
                "otp": "482910",
                "reference_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            }
        }
    }


class OTPVerifyResponse(BaseModel):
    """Response body for POST /api/v1/otp/verify."""

    access_token: str = Field(..., description="Short-lived JWT (10-minute validity)")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(default=600, description="Token validity in seconds")
    phone_number: str = Field(..., description="Verified phone number")


class OTPResendRequest(BaseModel):
    """Request body for POST /api/v1/otp/resend."""

    phone_number: str = Field(
        ...,
        description="Phone number to resend OTP to",
        examples=["+919876543210"],
    )
    reference_id: str = Field(
        ...,
        description="reference_id from the original /otp/send call",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )

    @field_validator("phone_number")
    @classmethod
    def validate_e164(cls, v: str) -> str:
        if not _PHONE_RE.match(v):
            raise ValueError("phone_number must be in E.164 format")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "phone_number": "+919876543210",
                "reference_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            }
        }
    }


class OTPResendResponse(BaseModel):
    """Response body for POST /api/v1/otp/resend."""

    message: str = Field(..., description="Status message")
    reference_id: str = Field(..., description="New reference_id for the resent OTP")
    retry_after: int = Field(
        ...,
        description="Seconds to wait before next resend is allowed (exponential backoff)",
    )
    expires_in: int = Field(..., description="New OTP validity in seconds")
    demo_otp: str | None = Field(default=None, description="Plaintext OTP returned for testing convenience")

