"""
Vercel Serverless Entry Point — FastAPI Wrap
===========================================
This file is the single entry point for Vercel (`api/index.py`).
"""

import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import the main FastAPI app instance from api.fastapi_app
from api.fastapi_app import app as fastapi_app

# Include root diagnostic endpoint GET /api/health
@fastapi_app.get(
    "/api/health",
    tags=["Health"],
    summary="Vercel Root Diagnostic Health Check",
    response_class=JSONResponse,
)
async def api_health() -> dict:
    """Returns 200 OK for Vercel diagnostic check."""
    return {"status": "ok", "service": "Microfinance API"}

# Vercel expects the ASGI callable to be named `app`
app = fastapi_app

# Local dev runner fallback
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.index:app", host="127.0.0.1", port=port, reload=True)