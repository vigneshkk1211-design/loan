"""
FastAPI Application — CrewAI Agent REST API
============================================
Mounts all three agent routers under /api/v1 and exposes:

  • Swagger UI  → /docs
  • ReDoc       → /redoc
  • OpenAPI JSON → /openapi.json

Routers:
  /api/v1/loan/calculate      — Accounting Agent (EMI)
  /api/v1/otp/send|verify|resend — Operations Agent (WhatsApp OTP)
  /api/v1/compliance/verify   — Compliance Agent (RBI FPC / KFS)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from api.routers import loan, otp, compliance as compliance_router

# Project root: api/fastapi_app.py → parent = api/ → parent.parent = project root
BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"

# ── App definition ────────────────────────────────────────────────────────────

app = FastAPI(
    title="NBFC CrewAI Agent API",
    description="""
## CrewAI-Powered NBFC/MFI Backend Services

Three specialized AI agents expose production-ready REST endpoints:

---

### 🧾 Accounting Agent
Flat-rate loan EMI calculation using Python `decimal.Decimal` with
`ROUND_HALF_UP` for exact paisa precision. No floating-point arithmetic
in any financial computation.

---

### 📱 Operations Agent
Secure WhatsApp OTP authentication workflow:
- Cryptographically random OTP via `secrets.randbelow`
- Salted HMAC-SHA256 storage (plaintext never persisted)
- 3-minute TTL, 3-attempt lockout
- Exponential backoff on resend
- Short-lived JWT (10-min) on successful verify

---

### ⚖️ Compliance Agent
RBI Fair Practices Code (FPC) enforcement:
- Key Fact Statement (KFS) generation (mandatory pre-disbursement)
- Delivery status state machine: `sent → delivered → read`
- **Hard gate**: loan approval BLOCKED without 4+ verified audit links
- Immutable 15-year audit trail (append-only JSON-lines + SHA-256)

---

**Base URL:** `/api/v1`
""",
    version="1.0.0",
    contact={
        "name": "NBFC API Team",
        "email": "api-support@example.com",
    },
    license_info={
        "name": "Proprietary",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Tighten allowed origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health endpoint ───────────────────────────────────────────────────────────

@app.get(
    "/health",
    tags=["Health"],
    summary="FastAPI health check",
    response_class=JSONResponse,
)
async def health() -> dict:
    """Returns 200 OK if the FastAPI service is running."""
    return {"status": "ok", "service": "nbfc-crewai-api", "version": "1.0.0"}


# ── Root info ─────────────────────────────────────────────────────────────────

@app.get(
    "/",
    tags=["Health"],
    summary="API root — available endpoints",
    response_class=JSONResponse,
    include_in_schema=False,
)
async def root() -> dict:
    return {
        "service": "NBFC CrewAI Agent API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "loan_calculate": "POST /api/v1/loan/calculate",
            "otp_send": "POST /api/v1/otp/send",
            "otp_verify": "POST /api/v1/otp/verify",
            "otp_resend": "POST /api/v1/otp/resend",
            "compliance_verify": "POST /api/v1/compliance/verify",
        },
    }


# ── Web Dashboard ─────────────────────────────────────────────────────────────

@app.get(
    "/dashboard",
    include_in_schema=False,
    summary="MicroFinance Web Dashboard",
)
async def dashboard() -> FileResponse:
    """Serve the interactive MicroFinance dashboard (HTML5 + TailwindCSS)."""
    return FileResponse(str(PUBLIC_DIR / "index.html"))


# ── Include routers ───────────────────────────────────────────────────────────

app.include_router(loan.router, prefix="/api/v1")
app.include_router(otp.router, prefix="/api/v1")
app.include_router(compliance_router.router, prefix="/api/v1")

# ── Static files (served before Flask catch-all in index.py) ──────────────────
# This MUST come after include_router() calls so route priority is preserved.
if (PUBLIC_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(PUBLIC_DIR / "static")), name="static")
