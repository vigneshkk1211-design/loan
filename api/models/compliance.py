"""
Pydantic request/response models for the RBI Compliance endpoint.

ComplianceVerifyRequest enforces that exactly 4+ audit links are supplied
before any approval can be granted (hard gate).
"""

from typing import List, Literal
from pydantic import BaseModel, Field, field_validator


class ComplianceVerifyRequest(BaseModel):
    """Request body for POST /api/v1/compliance/verify."""

    loan_id: str = Field(
        ...,
        description="Unique loan application identifier",
        examples=["LOAN-2024-00001"],
    )
    borrower_name: str = Field(
        ...,
        min_length=2,
        description="Full name of the borrower",
        examples=["Rajesh Kumar"],
    )
    principal: float = Field(
        ...,
        gt=0,
        description="Loan principal amount in INR",
        examples=[40000.0],
    )
    annual_rate: float = Field(
        ...,
        gt=0,
        le=100,
        description="Annual interest rate as a percentage",
        examples=[12.0],
    )
    tenure_months: int = Field(
        ...,
        gt=0,
        le=360,
        description="Loan tenure in months",
        examples=[12],
    )
    audit_links: List[str] = Field(
        ...,
        description=(
            "List of verifiable audit evidence URLs/references. "
            "HARD GATE: minimum 4 links required for approval."
        ),
        examples=[
            [
                "https://audit.example.com/doc/kfs-signed",
                "https://audit.example.com/doc/fpc-disclosure",
                "https://audit.example.com/doc/borrower-consent",
                "https://audit.example.com/doc/credit-check",
            ]
        ],
    )

    @field_validator("audit_links")
    @classmethod
    def must_have_minimum_links(cls, v: List[str]) -> List[str]:
        """Enforce a minimum of 1 link at model level; hard gate logic is in agent."""
        if not v:
            raise ValueError("audit_links must contain at least one entry")
        return [link.strip() for link in v if link.strip()]

    model_config = {
        "json_schema_extra": {
            "example": {
                "loan_id": "LOAN-2024-00001",
                "borrower_name": "Rajesh Kumar",
                "principal": 40000.0,
                "annual_rate": 12.0,
                "tenure_months": 12,
                "audit_links": [
                    "https://audit.example.com/doc/kfs-signed",
                    "https://audit.example.com/doc/fpc-disclosure",
                    "https://audit.example.com/doc/borrower-consent",
                    "https://audit.example.com/doc/credit-check",
                ],
            }
        }
    }


class KFSDocument(BaseModel):
    """Key Fact Statement as mandated by RBI FPC guidelines."""

    document_id: str
    generated_at: str
    loan_id: str
    borrower_name: str
    principal_inr: str
    annual_interest_rate_pct: str
    tenure_months: int
    monthly_emi_inr: str
    total_interest_inr: str
    total_payable_inr: str
    processing_fee_note: str
    grievance_redressal: str
    rbi_fpc_clause: str
    digital_signature: str


class AuditTrailEntry(BaseModel):
    """Single immutable audit trail record."""

    trail_id: str
    loan_id: str
    event: str
    actor: str
    timestamp_iso: str
    payload_hash: str
    retention_until: str


class ComplianceVerifyResponse(BaseModel):
    """Response body for POST /api/v1/compliance/verify."""

    loan_id: str = Field(..., description="Loan identifier echoed back")
    approved: bool = Field(..., description="Whether compliance gate was passed")
    reason: str = Field(..., description="Human-readable approval/rejection reason")
    kfs: KFSDocument = Field(..., description="Generated Key Fact Statement")
    delivery_status: Literal["sent", "delivered", "read"] = Field(
        ..., description="KFS delivery status tracking"
    )
    audit_trail_id: str = Field(..., description="Immutable audit trail record ID")
    audit_links_received: int = Field(
        ..., description="Number of audit links provided"
    )
    minimum_links_required: int = Field(
        default=4, description="Hard gate: minimum audit links for approval"
    )
    audit_trail_entry: AuditTrailEntry = Field(
        ..., description="The persisted audit trail record for this compliance check"
    )
