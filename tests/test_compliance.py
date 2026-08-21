"""
tests/test_compliance.py
========================
Unit tests for the Compliance Agent (api/agents/compliance.py).

Coverage:
  A. Hard Gate          — audit_links < 4 blocks approval; ≥ 4 passes
  B. KFS Generation     — all required fields, correct math, digital signature
  C. Delivery Tracker   — state machine sent → delivered → read → (terminal)
  D. Audit Trail        — entry structure, SHA-256 hash, 15-year retention,
                          approved/rejected events, audit_trail_id format
  E. verify_compliance  — full-function integration (gate + KFS + trail together)
"""

import hashlib
from datetime import datetime, timezone

import pytest

from api.agents.compliance import (
    MINIMUM_AUDIT_LINKS,
    advance_delivery_status,
    generate_kfs,
    get_delivery_status,
    verify_compliance,
    _delivery_store,
    _sha256,
    _round_inr,
)

# ── Shared fixtures ───────────────────────────────────────────────────────────

LOAN_ID   = "TEST-LOAN-001"
BORROWER  = "Rajesh Kumar"
PRINCIPAL = 40000.0
RATE      = 12.0
TENURE    = 12

FOUR_LINKS = [
    "https://audit.example.com/kfs-signed",
    "https://audit.example.com/fpc-disclosure",
    "https://audit.example.com/borrower-consent",
    "https://audit.example.com/credit-check",
]


def _verify(loan_id=LOAN_ID, borrower=BORROWER, principal=PRINCIPAL,
            rate=RATE, tenure=TENURE, links=None):
    """Shorthand wrapper around verify_compliance."""
    return verify_compliance(
        loan_id, borrower, principal, rate, tenure,
        links if links is not None else FOUR_LINKS,
    )


# ═══════════════════════════════ A. HARD GATE ═════════════════════════════════

class TestHardGate:
    """MINIMUM_AUDIT_LINKS must equal 4 (mandated by RBI FPC)."""

    def test_minimum_links_constant_is_4(self):
        assert MINIMUM_AUDIT_LINKS == 4

    @pytest.mark.parametrize("count", [0, 1, 2, 3])
    def test_fewer_than_4_links_blocks_approval(self, count):
        links = [f"https://example.com/{i}" for i in range(count)]
        result = _verify(loan_id=f"GATE-BLOCK-{count}", links=links)
        assert result["approved"] is False

    def test_exactly_4_links_passes_gate(self):
        result = _verify(links=FOUR_LINKS)
        assert result["approved"] is True

    def test_more_than_4_links_passes_gate(self):
        result = _verify(links=FOUR_LINKS + ["https://bonus.com/link"])
        assert result["approved"] is True

    def test_zero_links_rejection_reason_mentions_gate(self):
        result = _verify(loan_id="GATE-ZERO", links=[])
        reason = result["reason"].upper()
        assert "GATE" in reason or "MINIMUM" in reason or "BLOCKED" in reason

    def test_4_links_approval_reason_mentions_complian(self):
        result = _verify()
        assert any(word in result["reason"].lower() for word in ["complian", "verified", "confirmed"])

    def test_audit_links_received_count_is_correct(self):
        result = _verify(links=FOUR_LINKS[:3] + ["https://x.com"])
        # 4 links, gate passed
        assert result["audit_links_received"] == 4

    def test_minimum_links_required_returned_in_result(self):
        result = _verify()
        assert result["minimum_links_required"] == MINIMUM_AUDIT_LINKS

    def test_zero_links_received_count_is_zero(self):
        result = _verify(loan_id="ZERO-CT", links=[])
        assert result["audit_links_received"] == 0


# ═══════════════════════════════ B. KFS GENERATION ════════════════════════════

class TestKFSGeneration:
    REQUIRED_FIELDS = {
        "document_id", "generated_at", "loan_id", "borrower_name",
        "principal_inr", "annual_interest_rate_pct", "tenure_months",
        "monthly_emi_inr", "total_interest_inr", "total_payable_inr",
        "processing_fee_note", "grievance_redressal", "rbi_fpc_clause",
        "digital_signature",
    }

    def test_all_required_fields_present(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        assert self.REQUIRED_FIELDS.issubset(kfs.keys())

    def test_total_interest_correct(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        assert kfs["total_interest_inr"] == "4800.00"

    def test_total_payable_correct(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        assert kfs["total_payable_inr"] == "44800.00"

    def test_monthly_emi_correct(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        assert kfs["monthly_emi_inr"] == "3733.33"

    def test_borrower_name_preserved(self):
        kfs = generate_kfs(LOAN_ID, "Meena Devi", PRINCIPAL, RATE, TENURE)
        assert kfs["borrower_name"] == "Meena Devi"

    def test_loan_id_preserved(self):
        kfs = generate_kfs("LOAN-XYZ-999", BORROWER, PRINCIPAL, RATE, TENURE)
        assert kfs["loan_id"] == "LOAN-XYZ-999"

    def test_document_id_starts_with_kfs_prefix(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        assert kfs["document_id"].startswith("KFS-")

    def test_document_id_contains_loan_id(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        assert LOAN_ID in kfs["document_id"]

    def test_digital_signature_is_64_hex_chars(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        sig = kfs["digital_signature"]
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_different_loan_ids_produce_different_signatures(self):
        kfs1 = generate_kfs("LOAN-AAA", BORROWER, PRINCIPAL, RATE, TENURE)
        kfs2 = generate_kfs("LOAN-BBB", BORROWER, PRINCIPAL, RATE, TENURE)
        assert kfs1["digital_signature"] != kfs2["digital_signature"]

    def test_different_borrowers_produce_different_signatures(self):
        kfs1 = generate_kfs(LOAN_ID, "Rahul", PRINCIPAL, RATE, TENURE)
        kfs2 = generate_kfs(LOAN_ID, "Priya", PRINCIPAL, RATE, TENURE)
        assert kfs1["digital_signature"] != kfs2["digital_signature"]

    def test_rbi_clause_mentions_rbi(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        assert "RBI" in kfs["rbi_fpc_clause"]

    def test_grievance_contains_14448_or_rbi_url(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        assert "14448" in kfs["grievance_redressal"] or "rbi.org" in kfs["grievance_redressal"]

    def test_generated_at_is_valid_iso_utc(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        # Should parse without error
        dt = datetime.fromisoformat(kfs["generated_at"])
        assert dt.tzinfo is not None

    def test_principal_inr_matches_input(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, 75000.0, RATE, TENURE)
        assert kfs["principal_inr"] == "75000.00"

    def test_tenure_months_matches_input(self):
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, 24)
        assert kfs["tenure_months"] == 24

    def test_principal_plus_interest_equals_payable(self):
        """Mathematical coherence inside the KFS."""
        from decimal import Decimal
        kfs = generate_kfs(LOAN_ID, BORROWER, PRINCIPAL, RATE, TENURE)
        p = Decimal(kfs["principal_inr"])
        i = Decimal(kfs["total_interest_inr"])
        t = Decimal(kfs["total_payable_inr"])
        assert p + i == t


# ═══════════════════════════════ C. DELIVERY TRACKER ══════════════════════════

class TestDeliveryTracker:
    """
    State machine transitions:  sent → delivered → read  (read is terminal)
    Initial state for a newly created KFS is always "sent".
    """

    def _fresh_doc_id(self, suffix=""):
        """Create a fresh KFS and return its document_id."""
        kfs = generate_kfs(f"DL-{id(self)}{suffix}", BORROWER, PRINCIPAL, RATE, TENURE)
        # Ensure the delivery store tracks this doc starting at "sent"
        _delivery_store[kfs["document_id"]] = "sent"
        return kfs["document_id"]

    def test_initial_status_is_sent(self):
        doc_id = self._fresh_doc_id("-a")
        assert get_delivery_status(doc_id) == "sent"

    def test_advance_sent_to_delivered(self):
        doc_id = self._fresh_doc_id("-b")
        status = advance_delivery_status(doc_id)
        assert status == "delivered"

    def test_advance_delivered_to_read(self):
        doc_id = self._fresh_doc_id("-c")
        advance_delivery_status(doc_id)                  # sent → delivered
        status = advance_delivery_status(doc_id)         # delivered → read
        assert status == "read"

    def test_read_is_terminal_state(self):
        doc_id = self._fresh_doc_id("-d")
        advance_delivery_status(doc_id)                  # sent → delivered
        advance_delivery_status(doc_id)                  # delivered → read
        status = advance_delivery_status(doc_id)         # read → read (terminal)
        assert status == "read"

    def test_get_delivery_status_after_advance(self):
        doc_id = self._fresh_doc_id("-e")
        advance_delivery_status(doc_id)
        assert get_delivery_status(doc_id) == "delivered"

    def test_verify_compliance_sets_initial_status_sent(self):
        result = _verify(loan_id="DL-INIT")
        assert result["delivery_status"] == "sent"

    def test_unknown_doc_id_defaults_to_sent(self):
        assert get_delivery_status("unknown-kfs-id-xyz") == "sent"


# ═══════════════════════════════ D. AUDIT TRAIL ════════════════════════════════

class TestAuditTrail:
    def test_audit_trail_entry_present_in_result(self):
        result = _verify()
        assert "audit_trail_entry" in result
        assert result["audit_trail_entry"] is not None

    def test_audit_trail_entry_has_required_fields(self):
        entry = _verify()["audit_trail_entry"]
        required = {
            "trail_id", "loan_id", "event", "actor",
            "timestamp_iso", "payload_hash", "retention_until",
        }
        assert required.issubset(entry.keys())

    def test_payload_hash_is_64_hex_chars(self):
        entry = _verify()["audit_trail_entry"]
        h = entry["payload_hash"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_approved_event_name(self):
        entry = _verify()["audit_trail_entry"]
        assert "APPROVED" in entry["event"]

    def test_rejected_event_name(self):
        entry = _verify(loan_id="REJECT-EVT", links=[])["audit_trail_entry"]
        assert "REJECTED" in entry["event"]

    def test_actor_is_compliance_agent(self):
        entry = _verify()["audit_trail_entry"]
        assert "compliance_agent" in entry["actor"]

    def test_audit_trail_id_format(self):
        result = _verify()
        assert result["audit_trail_id"].startswith("AUDIT-")

    def test_retention_until_is_approx_15_years(self):
        entry = _verify()["audit_trail_entry"]
        retention_dt = datetime.fromisoformat(entry["retention_until"])
        now = datetime.now(timezone.utc)
        years_diff = (retention_dt - now).days / 365
        assert 14.9 < years_diff < 15.1, (
            f"Expected ~15 years retention, got {years_diff:.2f} years"
        )

    def test_timestamp_is_valid_utc_iso(self):
        entry = _verify()["audit_trail_entry"]
        dt = datetime.fromisoformat(entry["timestamp_iso"])
        assert dt.tzinfo is not None

    def test_loan_id_in_audit_entry(self):
        result = _verify(loan_id="LOAN-AUDIT-CHECK")
        assert result["audit_trail_entry"]["loan_id"] == "LOAN-AUDIT-CHECK"

    def test_payload_hash_changes_with_different_loan(self):
        """Different payload → different SHA-256 hash (tamper-evidence check)."""
        h1 = _verify(loan_id="HASH-A")["audit_trail_entry"]["payload_hash"]
        h2 = _verify(loan_id="HASH-B")["audit_trail_entry"]["payload_hash"]
        assert h1 != h2


# ═══════════════════════════════ E. SHA256 HELPER ═════════════════════════════

class TestSHA256Helper:
    def test_known_value(self):
        """SHA-256 of 'abc' is well-known."""
        expected = "ba7816bf8f01cfea414140de5dae2ec73b00361bbef0469348423f656b66a8a5"
        assert _sha256("abc") == expected

    def test_empty_string(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert _sha256("") == expected

    def test_output_length_is_64(self):
        assert len(_sha256("any text")) == 64

    def test_different_inputs_different_hashes(self):
        assert _sha256("loan-A") != _sha256("loan-B")


# ═══════════════════════════════ F. ROUND_INR HELPER ══════════════════════════

class TestRoundINR:
    def test_rounds_to_2_decimal_places(self):
        assert _round_inr(3733.333333) == "3733.33"

    def test_round_half_up(self):
        assert _round_inr(3733.335) == "3733.34"   # rounds up

    def test_exact_value_unchanged(self):
        assert _round_inr(4800.00) == "4800.00"

    def test_zero(self):
        assert _round_inr(0.0) == "0.00"
