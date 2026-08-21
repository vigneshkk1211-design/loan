"""
Router: Loan Calculation
Route: POST /api/v1/loan/calculate

Delegates to the Accounting Agent for flat-rate EMI computation
using Python Decimal with ROUND_HALF_UP paisa precision.
"""

from fastapi import APIRouter, HTTPException, status
from decimal import Decimal

from api.agents.accounting import calculate_emi
from api.models.loan import LoanRequest, LoanResponse

router = APIRouter(
    prefix="/loan",
    tags=["Accounting Agent — Loan Calculation"],
)


@router.post(
    "/calculate",
    response_model=LoanResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate Flat-Rate Loan EMI",
    description="""
Compute the Equal Monthly Instalment (EMI) for a flat-rate loan.

**Calculation method:** Flat-rate interest (common in MFI / NBFC field lending)

```
Total Interest  = Principal × (Annual Rate / 100) × (Tenure / 12)
Total Payable   = Principal + Total Interest
Monthly EMI     = Total Payable / Tenure
```

All arithmetic uses Python `decimal.Decimal` with `ROUND_HALF_UP` to the
nearest paisa (₹ 0.01), ensuring lossless precision in financial contexts.

**Example:** ₹40,000 at 12% flat for 12 months
- Total Interest = ₹4,800.00
- Total Payable  = ₹44,800.00
- Monthly EMI    = ₹3,733.33
""",
    responses={
        200: {"description": "EMI calculated successfully"},
        422: {"description": "Validation error (invalid input values)"},
        500: {"description": "Internal calculation error"},
    },
)
async def calculate_loan_emi(body: LoanRequest) -> LoanResponse:
    """
    Calculate flat-rate loan EMI with exact paisa precision.

    - **principal**: Loan amount in INR (must be > 0)
    - **annual_rate**: Annual flat interest rate as % (0 < rate ≤ 100)
    - **tenure_months**: Repayment duration in months (1–360)
    """
    try:
        result = calculate_emi(
            principal=body.principal,
            annual_rate=body.annual_rate,
            tenure_months=body.tenure_months,
        )
        return LoanResponse(**result)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Calculation error: {exc}",
        ) from exc
