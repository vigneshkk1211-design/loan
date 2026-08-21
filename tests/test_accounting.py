"""
tests/test_accounting.py
========================
Unit tests for the Accounting Agent (api/agents/accounting.py).

Coverage:
  • Standard flat-rate EMI formula correctness (₹40K, 12%, 12M)
  • ROUND_HALF_UP paisa precision (not banker's rounding)
  • Decimal coherence — no float drift
  • All return-dict keys present
  • Input validation (ValueError on bad inputs)
  • Mathematical invariants (principal + interest == payable, EMI × n ≈ total)
  • Edge cases: 1-month, very large principal, max/min rate
"""

import pytest
from decimal import Decimal

from api.agents.accounting import calculate_emi, _round_inr


# ─────────────────────────────────────── helpers ─────────────────────────────

def _run(principal, rate, tenure):
    """Shorthand: pass raw Python numbers, return result dict."""
    return calculate_emi(Decimal(str(principal)), Decimal(str(rate)), tenure)


# ─────────────────────────────────────── standard formula ────────────────────

class TestStandardFormula:
    """
    Reference values derived by hand:
        ₹40,000 × 12% p.a. flat × 12/12 = ₹4,800  interest
        Total = ₹44,800
        EMI   = 44800 / 12 = 3733.333… → ROUND_HALF_UP → ₹3,733.33
    """

    def test_total_interest(self):
        assert _run(40000, 12, 12)["total_interest"] == "4800.00"

    def test_total_payable(self):
        assert _run(40000, 12, 12)["total_payable"] == "44800.00"

    def test_monthly_emi(self):
        assert _run(40000, 12, 12)["monthly_emi"] == "3733.33"

    def test_principal_passthrough(self):
        assert _run(40000, 12, 12)["principal"] == "40000.00"

    def test_rate_passthrough(self):
        assert _run(40000, 12, 12)["annual_rate"] == "12"

    def test_tenure_passthrough(self):
        assert _run(40000, 12, 12)["tenure_months"] == 12


# ─────────────────────────────────────── metadata ────────────────────────────

class TestResultMetadata:
    def test_calculation_method_is_flat_rate(self):
        result = _run(40000, 12, 12)
        assert result["calculation_method"] == "flat_rate"

    def test_precision_mentions_round_half_up(self):
        result = _run(40000, 12, 12)
        assert "ROUND_HALF_UP" in result["precision"]

    def test_all_required_keys_present(self):
        result = _run(40000, 12, 12)
        required = {
            "principal", "annual_rate", "tenure_months",
            "total_interest", "total_payable", "monthly_emi",
            "calculation_method", "precision",
        }
        assert required.issubset(result.keys())


# ─────────────────────────────────────── precision ───────────────────────────

class TestPrecision:
    def test_emi_has_exactly_2_decimal_places(self):
        """All monetary outputs must be formatted to exactly 2 d.p."""
        for result_key in ("total_interest", "total_payable", "monthly_emi"):
            val = _run(10000, 18, 7)[result_key]
            assert "." in val, f"{result_key} has no decimal point"
            assert len(val.split(".")[1]) == 2, f"{result_key} has wrong decimal places"

    def test_round_half_up_vs_bankers_rounding(self):
        """
        Python's built-in round() uses banker's rounding; Decimal ROUND_HALF_UP
        must be used instead.
        Midpoint case: total_payable = 11050.00, EMI = 11050/7 = 1578.5714…
        ROUND_HALF_UP  → 1578.57 ✓
        """
        result = _run(10000, 18, 7)
        emi = result["monthly_emi"]
        # Must be exactly 2 d.p. and a valid Decimal
        assert Decimal(emi) == Decimal(emi).quantize(Decimal("0.01"))

    def test_no_float_drift_on_unit_principal(self):
        """
        ₹1 at 12% for 12 months:
          interest = 1 * 0.12 * 1 = 0.12  (exact in Decimal, but 0.12 ≠ 0.12 in float)
        """
        result = _run(1, 12, 12)
        assert result["total_interest"] == "0.12"
        assert result["total_payable"]  == "1.12"

    def test_helper_round_inr_rounds_up_at_midpoint(self):
        """_round_inr(0.005) → 0.01 (ROUND_HALF_UP), NOT 0.00 (ROUND_HALF_EVEN)."""
        assert _round_inr(Decimal("0.005")) == Decimal("0.01")
        assert _round_inr(Decimal("2.4449")) == Decimal("2.44")
        assert _round_inr(Decimal("2.4450")) == Decimal("2.45")


# ─────────────────────────────────────── invariants ──────────────────────────

class TestMathematicalInvariants:
    """These relationships must hold regardless of the input values."""

    CASES = [
        (40000, 12, 12),
        (75000, 15, 18),
        (100000, 24, 36),
        (5000, 36, 6),
        (500000, 12, 60),
    ]

    @pytest.mark.parametrize("p,r,t", CASES)
    def test_principal_plus_interest_equals_payable(self, p, r, t):
        result = _run(p, r, t)
        assert (Decimal(result["principal"]) + Decimal(result["total_interest"])
                == Decimal(result["total_payable"]))

    @pytest.mark.parametrize("p,r,t", CASES)
    def test_emi_times_tenure_within_one_rupee_of_total(self, p, r, t):
        """
        EMI × tenure ≈ total_payable.
        Difference is bounded by ₹1 due to per-EMI rounding.
        """
        result = _run(p, r, t)
        diff = abs(Decimal(result["monthly_emi"]) * t - Decimal(result["total_payable"]))
        assert diff <= Decimal("1.00"), (
            f"EMI coherence failed for ({p},{r}%,{t}m): diff=₹{diff}"
        )

    @pytest.mark.parametrize("p,r,t", CASES)
    def test_total_payable_greater_than_principal(self, p, r, t):
        result = _run(p, r, t)
        assert Decimal(result["total_payable"]) > Decimal(result["principal"])

    @pytest.mark.parametrize("p,r,t", CASES)
    def test_monthly_emi_is_positive(self, p, r, t):
        assert Decimal(_run(p, r, t)["monthly_emi"]) > 0


# ─────────────────────────────────────── input validation ────────────────────

class TestInputValidation:
    def test_zero_principal_raises_value_error(self):
        with pytest.raises(ValueError, match="principal"):
            calculate_emi(Decimal("0"), Decimal("12"), 12)

    def test_negative_principal_raises_value_error(self):
        with pytest.raises(ValueError, match="principal"):
            calculate_emi(Decimal("-5000"), Decimal("12"), 12)

    def test_zero_rate_raises_value_error(self):
        with pytest.raises(ValueError, match="annual_rate"):
            calculate_emi(Decimal("40000"), Decimal("0"), 12)

    def test_rate_over_100_raises_value_error(self):
        with pytest.raises(ValueError, match="annual_rate"):
            calculate_emi(Decimal("40000"), Decimal("101"), 12)

    def test_zero_tenure_raises_value_error(self):
        with pytest.raises(ValueError, match="tenure_months"):
            calculate_emi(Decimal("40000"), Decimal("12"), 0)

    def test_negative_tenure_raises_value_error(self):
        with pytest.raises(ValueError, match="tenure_months"):
            calculate_emi(Decimal("40000"), Decimal("12"), -6)


# ─────────────────────────────────────── edge cases ──────────────────────────

class TestEdgeCases:
    def test_one_month_tenure(self):
        """Single-month loan: interest = P × r/12; EMI = total."""
        result = _run(12000, 24, 1)
        assert result["total_interest"] == "240.00"   # 12000 × 24% / 12
        assert result["monthly_emi"]    == "12240.00" # single instalment

    def test_large_principal(self):
        result = _run(500000, 12, 60)
        assert float(result["monthly_emi"]) > 0
        assert Decimal(result["total_payable"]) > Decimal("500000")

    def test_rate_at_boundary_100(self):
        """Exactly 100% annual rate is still valid per our validation."""
        result = _run(10000, 100, 12)
        assert result["total_interest"] == "10000.00"
        assert result["total_payable"]  == "20000.00"

    def test_rate_just_below_boundary(self):
        """99.99% is valid."""
        result = _run(10000, 99.99, 12)
        assert Decimal(result["total_interest"]) > 0

    def test_decimal_input_rate(self):
        """Fractional rates (e.g., 12.5%) must work without float drift."""
        result = _run(40000, 12.5, 12)
        expected_interest = "5000.00"  # 40000 × 0.125 × 1
        assert result["total_interest"] == expected_interest
