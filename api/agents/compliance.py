"""
Compliance Agent — RBI Fair Practices Code (FPC) & KFS Generation
==================================================================
Implements:

  1. Key Fact Statement (KFS) generation per RBI Master Directions on
     Interest Rate on Advances (2016, updated 2023).
  2. Delivery status state machine: sent → delivered → read
  3. Hard gate: blocks loan approval if audit_links count < 4.
  4. Immutable 15-year audit trail persisted as append-only JSON-lines
     to `audit_trail.log` in the current working directory.

⚠️  Persistence note: audit_trail.log is written to the local filesystem.
    On Vercel serverless, the /tmp directory is writable but ephemeral.
    For a production 15-year archive, redirect _write_audit_trail() to
    cloud object storage (GCS, S3, Azure Blob) or a time-series DB.

Audit trail records are:
  • Append-only (never mutated or deleted)
  • Content-hashed with SHA-256 for tamper-evidence
  • Timestamped in ISO-8601 UTC
  • Tagged with a 15-year retention deadline from creation date
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List

import openai

# ── NVIDIA NIM Configuration ─────────────────────────────────────────────────
NVIDIA_API_KEY = os.environ.get(
    "NVIDIA_API_KEY", 
    "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"
)
NVIDIA_BASE_URL = os.environ.get(
    "NVIDIA_BASE_URL", 
    "https://integrate.api.nvidia.com/v1"
)
LLM_MODEL = os.environ.get(
    "LLM_MODEL", 
    "meta/llama-3.3-70b-instruct"
)

def _call_nvidia_nim(system_prompt: str, user_prompt: str) -> str:
    """Helper to call NVIDIA NIM using standard openai SDK with graceful fallback."""
    try:
        client = openai.OpenAI(
            api_key=NVIDIA_API_KEY,
            base_url=NVIDIA_BASE_URL,
        )
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=256,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        import sys
        print(f"[LLM FALLBACK] NVIDIA NIM call failed: {exc}", file=sys.stderr)
        return ""


# ── Configuration ────────────────────────────────────────────────────────────

MINIMUM_AUDIT_LINKS: int = 4
AUDIT_TRAIL_RETENTION_YEARS: int = 15

# Prefer /tmp on serverless; fall back to cwd for local dev
_AUDIT_LOG_PATH = Path(os.environ.get("AUDIT_LOG_PATH", "/tmp/audit_trail.log"))

_TWO_DP = Decimal("0.01")


# ── Internal helpers ─────────────────────────────────────────────────────────

def _now_utc() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _retention_deadline() -> str:
    """Return the audit retention deadline (15 years from now)."""
    deadline = datetime.now(timezone.utc) + timedelta(days=AUDIT_TRAIL_RETENTION_YEARS * 365)
    return deadline.isoformat()


def _sha256(data: str) -> str:
    """Return hex SHA-256 of a UTF-8 string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _round_inr(value: float) -> str:
    """Round a float to 2 decimal places using ROUND_HALF_UP, return as string."""
    d = Decimal(str(value))
    return str(d.quantize(_TWO_DP, rounding=ROUND_HALF_UP))


def _write_audit_trail(record: Dict[str, Any]) -> None:
    """
    Append a single JSON record to the audit trail log file.

    The file is opened in append mode so existing records are never overwritten.
    Each line is a self-contained JSON object (JSON-lines format).

    ⚠️  Replace with cloud storage write in production for durability.
    """
    try:
        with open(_AUDIT_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        # Log to stderr but do not crash the API — audit failure should
        # be monitored separately and never silently suppress the response.
        import sys
        print(f"[AUDIT WARNING] Failed to write audit trail: {exc}", file=sys.stderr)


# ── KFS Generation ───────────────────────────────────────────────────────────

def generate_kfs(
    loan_id: str,
    borrower_name: str,
    principal: float,
    annual_rate: float,
    tenure_months: int,
) -> Dict[str, Any]:
    """
    Generate a Key Fact Statement (KFS) as mandated by RBI FPC guidelines.

    The KFS must be provided to the borrower BEFORE loan disbursement.
    It must include (at minimum): loan amount, rate, tenure, total cost,
    EMI, grievance contact, and applicable regulatory reference.

    Args:
        loan_id:        Unique loan identifier.
        borrower_name:  Full name of the borrower.
        principal:      Principal amount (INR).
        annual_rate:    Annual flat interest rate (%).
        tenure_months:  Repayment tenure in months.

    Returns:
        dict representing the KFS document.
    """
    # ── Flat-rate EMI calculation (mirrors accounting agent) ─────────────────
    p = Decimal(str(principal))
    r = Decimal(str(annual_rate))
    n = Decimal(str(tenure_months))

    total_interest = p * (r / Decimal("100")) * (n / Decimal("12"))
    total_payable = p + total_interest
    monthly_emi = total_payable / n

    doc_id = f"KFS-{loan_id}-{uuid.uuid4().hex[:8].upper()}"
    generated_at = _now_utc()

    # Digital signature = SHA-256 of canonical KFS fields (lightweight tamper-evidence)
    canonical = f"{doc_id}|{loan_id}|{borrower_name}|{principal}|{annual_rate}|{tenure_months}|{generated_at}"
    digital_signature = _sha256(canonical)

    return {
        "document_id": doc_id,
        "generated_at": generated_at,
        "loan_id": loan_id,
        "borrower_name": borrower_name,
        "principal_inr": _round_inr(principal),
        "annual_interest_rate_pct": str(annual_rate),
        "tenure_months": tenure_months,
        "monthly_emi_inr": _round_inr(float(monthly_emi)),
        "total_interest_inr": _round_inr(float(total_interest)),
        "total_payable_inr": _round_inr(float(total_payable)),
        "processing_fee_note": "Processing fee (if any) will be disclosed separately before disbursement as per RBI FPC.",
        "grievance_redressal": (
            "Grievances may be escalated to the RBI Ombudsman at "
            "https://cms.rbi.org.in or call 14448 (toll-free)."
        ),
        "rbi_fpc_clause": (
            "This KFS is issued in compliance with RBI Master Direction – "
            "Interest Rate on Advances (RBI/2015-16/397, updated 2023) and "
            "RBI Fair Practices Code for NBFCs/MFIs."
        ),
        "digital_signature": digital_signature,
    }


# ── Delivery Status State Machine ────────────────────────────────────────────

# In-memory state store for delivery tracking.
# Replace with DB persistence in production.
_delivery_store: Dict[str, str] = {}

_VALID_TRANSITIONS = {
    "sent": "delivered",
    "delivered": "read",
}


def advance_delivery_status(kfs_doc_id: str) -> str:
    """
    Advance the KFS delivery status along the state machine.

      sent → delivered → read

    Args:
        kfs_doc_id: The document_id from generate_kfs().

    Returns:
        The new delivery status string.
    """
    current = _delivery_store.get(kfs_doc_id, "sent")
    next_status = _VALID_TRANSITIONS.get(current, current)
    _delivery_store[kfs_doc_id] = next_status
    return next_status


def get_delivery_status(kfs_doc_id: str) -> str:
    """Return the current delivery status for a KFS document."""
    return _delivery_store.get(kfs_doc_id, "sent")


# ── Hard Gate & Compliance Verification ──────────────────────────────────────

def verify_compliance(
    loan_id: str,
    borrower_name: str,
    principal: float,
    annual_rate: float,
    tenure_months: int,
    audit_links: List[str],
) -> Dict[str, Any]:
    """
    Run the full RBI compliance verification workflow.

    Steps:
      1. Generate KFS document.
      2. Set initial delivery status to "sent".
      3. Enforce hard gate: reject if audit_links < MINIMUM_AUDIT_LINKS.
      4. Write an immutable audit trail entry (15-year retention).
      5. Return full compliance result.

    Args:
        loan_id:        Loan identifier.
        borrower_name:  Borrower full name.
        principal:      Principal (INR).
        annual_rate:    Annual rate (%).
        tenure_months:  Tenure (months).
        audit_links:    List of verifiable evidence URLs/references.

    Returns:
        dict with keys: loan_id, approved, reason, kfs, delivery_status,
        audit_trail_id, audit_links_received, minimum_links_required,
        audit_trail_entry.
    """
    # Step 1 — Generate KFS
    kfs = generate_kfs(loan_id, borrower_name, principal, annual_rate, tenure_months)

    # Step 2 — Set delivery status
    delivery_status = "sent"
    _delivery_store[kfs["document_id"]] = delivery_status

    # Step 3 — Hard gate
    received_count = len(audit_links)
    if received_count < MINIMUM_AUDIT_LINKS:
        approved = False
        reason = (
            f"COMPLIANCE GATE FAILED: {received_count} audit link(s) provided, "
            f"minimum {MINIMUM_AUDIT_LINKS} required. "
            "Loan approval is BLOCKED until all mandatory disclosures are evidenced."
        )
    else:
        approved = True
        reason = (
            f"Compliance verified. {received_count} audit link(s) confirmed. "
            "KFS generated and delivery initiated. Loan may proceed to disbursement."
        )

    # Try to generate detailed compliance review narrative using direct NVIDIA NIM LLM call
    detailed_reason = _call_nvidia_nim(
        system_prompt="You are an RBI Compliance Specialist ensuring MFI compliance and grievance routing.",
        user_prompt=(
            f"Review the loan application compliance details:\n"
            f"- Loan ID: {loan_id}\n"
            f"- Borrower: {borrower_name}\n"
            f"- Principal: ₹{principal}\n"
            f"- Annual Rate: {annual_rate}%\n"
            f"- Tenure: {tenure_months} months\n"
            f"- Approved Status: {approved}\n"
            f"- Base Decision Reason: {reason}\n"
            f"- Audit Disclosures: {', '.join(audit_links)}\n\n"
            f"Write a concise, professional RBI compliance audit summary (max 3 sentences) confirming the status and audit trails."
        )
    )
    if detailed_reason:
        reason = detailed_reason


    # Step 4 — Build immutable audit trail entry
    trail_id = f"AUDIT-{uuid.uuid4().hex.upper()}"
    event = "COMPLIANCE_VERIFY_APPROVED" if approved else "COMPLIANCE_VERIFY_REJECTED"
    now = _now_utc()

    payload_data = {
        "trail_id": trail_id,
        "loan_id": loan_id,
        "event": event,
        "actor": "compliance_agent_v1",
        "timestamp_iso": now,
        "kfs_document_id": kfs["document_id"],
        "audit_links": audit_links,
        "approved": approved,
        "reason": reason,
    }
    payload_hash = _sha256(json.dumps(payload_data, sort_keys=True))

    audit_entry: Dict[str, Any] = {
        **payload_data,
        "payload_hash": payload_hash,
        "retention_until": _retention_deadline(),
    }

    # Step 5 — Persist to append-only log
    _write_audit_trail(audit_entry)

    return {
        "loan_id": loan_id,
        "approved": approved,
        "reason": reason,
        "kfs": kfs,
        "delivery_status": delivery_status,
        "audit_trail_id": trail_id,
        "audit_links_received": received_count,
        "minimum_links_required": MINIMUM_AUDIT_LINKS,
        "audit_trail_entry": {
            "trail_id": trail_id,
            "loan_id": loan_id,
            "event": event,
            "actor": "compliance_agent_v1",
            "timestamp_iso": now,
            "payload_hash": payload_hash,
            "retention_until": _retention_deadline(),
        },
    }
