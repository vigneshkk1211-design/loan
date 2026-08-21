"""
Pydantic request/response models for the Loan Accounting endpoint.

All monetary fields use `Decimal` strings so JSON serialization
is lossless — never float in financial APIs.
"""

from decimal import Decimal
from pydantic import BaseModel, Field, field_validator


class LoanRequest(BaseModel):
    """Request body for POST /api/v1/loan/calculate."""

    principal: Decimal = Field(
        ...,
        gt=0,
        description="Loan principal amount in INR (e.g. 40000)",
        examples=[40000],
    )
    annual_rate: Decimal = Field(
        ...,
        gt=0,
        le=100,
        description="Annual flat interest rate as a percentage (e.g. 12.0 for 12%)",
        examples=[12.0],
    )
    tenure_months: int = Field(
        ...,
        gt=0,
        le=360,
        description="Loan repayment tenure in months (e.g. 12)",
        examples=[12],
    )

    @field_validator("principal", "annual_rate", mode="before")
    @classmethod
    def coerce_to_decimal(cls, v: object) -> Decimal:
        """Accept int/float from JSON and convert to Decimal safely."""
        return Decimal(str(v))

    model_config = {
        "json_schema_extra": {
            "example": {
                "principal": 40000,
                "annual_rate": 12.0,
                "tenure_months": 12,
            }
        }
    }


class LoanResponse(BaseModel):
    """Response body for POST /api/v1/loan/calculate."""

    principal: str = Field(..., description="Original principal (INR)")
    annual_rate: str = Field(..., description="Annual interest rate (%)")
    tenure_months: int = Field(..., description="Repayment tenure (months)")
    total_interest: str = Field(..., description="Total flat interest charged (INR)")
    total_payable: str = Field(..., description="Total amount payable = principal + interest (INR)")
    monthly_emi: str = Field(..., description="Equal Monthly Instalment (INR)")
    calculation_method: str = Field(
        default="flat_rate",
        description="Interest calculation method used",
    )
    precision: str = Field(
        default="ROUND_HALF_UP to 2 decimal places",
        description="Rounding strategy applied",
    )
