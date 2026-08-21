"""
Router: RBI Compliance Verification
Route: POST /api/v1/compliance/verify

Delegates to the Compliance Agent for:
  - Key Fact Statement (KFS) generation (RBI FPC mandated)
  - Delivery status tracking (sent → delivered → read)
  - Hard gate enforcement (min 4 audit links)
  - Immutable 15-year audit trail logging
"""

from fastapi import APIRouter, HTTPException, status

from api.agents.compliance import verify_compliance
from api.models.compliance import (
    AuditTrailEntry,
    ComplianceVerifyRequest,
    ComplianceVerifyResponse,
    KFSDocument,
)

router = APIRouter(
    prefix="/compliance",
    tags=["Compliance Agent — RBI FPC & KFS"],
)


@router.post(
    "/verify",
    response_model=ComplianceVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="RBI Compliance Verification & KFS Generation",
    description="""
Runs the full RBI Fair Practices Code (FPC) compliance workflow:

**Step 1 — KFS Generation**
Generates a Key Fact Statement as mandated by RBI Master Direction –
Interest Rate on Advances (RBI/2015-16/397, updated 2023). Includes:
principal, rate, EMI, total cost, grievance contact, digital signature.

**Step 2 — Delivery Status**
Sets initial delivery status to `sent`. Advance via state machine:
```
sent → delivered → read
```

**Step 3 — Hard Gate 🔒**
```
if len(audit_links) < 4:
    approved = False  # loan BLOCKED
```
A minimum of **4 verified audit evidence links** must be provided.
No exceptions. This gate cannot be bypassed.

**Required audit links (examples):**
- KFS signed copy URL
- FPC disclosure acknowledgement
- Borrower consent record
- Credit assessment report

**Step 4 — Immutable Audit Trail**
Every compliance verification (approved or rejected) writes an
append-only record to `audit_trail.log` (JSON-lines format) with:
- SHA-256 content hash (tamper-evidence)
- ISO-8601 UTC timestamp
- 15-year retention deadline
""",
    responses={
        200: {
            "description": (
                "Compliance check complete. Check `approved` field — "
                "False means the loan is BLOCKED."
            )
        },
        422: {"description": "Validation error (missing or malformed fields)"},
        500: {"description": "Internal compliance engine error"},
    },
)
async def verify(body: ComplianceVerifyRequest) -> ComplianceVerifyResponse:
    """
    - **loan_id**: Unique loan application ID
    - **borrower_name**: Full name of the borrower (min 2 chars)
    - **principal**: Loan principal in INR (> 0)
    - **annual_rate**: Annual flat interest rate % (0–100)
    - **tenure_months**: Repayment period in months (1–360)
    - **audit_links**: List of evidence URLs — **minimum 4 required**
    """
    try:
        result = verify_compliance(
            loan_id=body.loan_id,
            borrower_name=body.borrower_name,
            principal=body.principal,
            annual_rate=body.annual_rate,
            tenure_months=body.tenure_months,
            audit_links=body.audit_links,
        )

        # Build typed response
        kfs_doc = KFSDocument(**result["kfs"])
        audit_entry = AuditTrailEntry(**result["audit_trail_entry"])

        return ComplianceVerifyResponse(
            loan_id=result["loan_id"],
            approved=result["approved"],
            reason=result["reason"],
            kfs=kfs_doc,
            delivery_status=result["delivery_status"],
            audit_trail_id=result["audit_trail_id"],
            audit_links_received=result["audit_links_received"],
            minimum_links_required=result["minimum_links_required"],
            audit_trail_entry=audit_entry,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Compliance verification error: {exc}",
        ) from exc
