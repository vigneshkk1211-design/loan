"""
Accounting Agent — Loan EMI Calculation Engine
===============================================
Uses Python's `decimal` module with ROUND_HALF_UP for exact paisa precision.

Calculation method: Flat-rate interest (common in MFI/NBFC field lending).

  Total Interest   = Principal × (Annual Rate / 100) × (Tenure / 12)
  Total Payable    = Principal + Total Interest
  Monthly EMI      = Total Payable / Tenure (months)

All intermediate values are computed as Decimal and rounded to 2 decimal
places (paisa) only at the final output stage to avoid compounding errors.
"""

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Dict, Any

# Set high precision for intermediate calculations; round only at output
getcontext().prec = 28


_TWO_PLACES = Decimal("0.01")


def _round_inr(value: Decimal) -> Decimal:
    """Round a Decimal to 2 decimal places (nearest paisa) using ROUND_HALF_UP."""
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_emi(
    principal: Decimal,
    annual_rate: Decimal,
    tenure_months: int,
) -> Dict[str, Any]:
    """
    Compute flat-rate loan EMI with exact paisa precision.

    Args:
        principal:      Loan amount in INR (Decimal).
        annual_rate:    Annual interest rate as a percentage (e.g. Decimal("12.0")).
        tenure_months:  Repayment tenure in months (int).

    Returns:
        A dict with keys:
          - principal           : str  (INR)
          - annual_rate         : str  (%)
          - tenure_months       : int
          - total_interest      : str  (INR)
          - total_payable       : str  (INR)
          - monthly_emi         : str  (INR)
          - calculation_method  : str
          - precision           : str

    Raises:
        ValueError: If any input is non-positive.
    """
    if principal <= 0:
        raise ValueError("principal must be greater than zero")
    if annual_rate <= 0 or annual_rate > 100:
        raise ValueError("annual_rate must be between 0 and 100")
    if tenure_months <= 0:
        raise ValueError("tenure_months must be greater than zero")

    # ── Core flat-rate formulas ──────────────────────────────────────────────
    # Convert rate to per-year fraction, then pro-rate for tenure
    total_interest: Decimal = (
        principal
        * (annual_rate / Decimal("100"))
        * (Decimal(tenure_months) / Decimal("12"))
    )

    total_payable: Decimal = principal + total_interest

    # EMI = Total Payable / Tenure; individual EMI rounded to nearest paisa
    monthly_emi: Decimal = total_payable / Decimal(tenure_months)

    # ── Round output values ──────────────────────────────────────────────────
    r_interest = _round_inr(total_interest)
    r_payable = _round_inr(total_payable)
    r_emi = _round_inr(monthly_emi)

    return {
        "principal": str(_round_inr(principal)),
        "annual_rate": str(annual_rate),
        "tenure_months": tenure_months,
        "total_interest": str(r_interest),
        "total_payable": str(r_payable),
        "monthly_emi": str(r_emi),
        "calculation_method": "flat_rate",
        "precision": "ROUND_HALF_UP to 2 decimal places",
    }
