@echo off
title FinFlow NBFC Server
color 0A
echo.
echo  ================================================
echo   FinFlow NBFC - Starting Server...
echo  ================================================
echo.

:: Change to the project directory (same folder as this .bat file)
cd /d "%~dp0"

echo [1/3] Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

echo.
echo [2/3] Installing dependencies...
pip install fastapi "uvicorn[standard]" flask openai pydantic "python-jose[cryptography]" a2wsgi httpx python-dotenv 2>nul
if errorlevel 1 (
    echo WARNING: Some packages may have failed. Trying to start anyway...
)

echo.
echo [3/3] Starting FastAPI server...
echo.
echo  ================================================
echo   Dashboard  : http://127.0.0.1:8000/dashboard
echo   Swagger UI : http://127.0.0.1:8000/docs
echo   Health     : http://127.0.0.1:8000/health
echo  ================================================
echo.
echo  Press CTRL+C to stop the server.
echo.

:: Set a dummy SECRET_KEY if .env doesn't exist
if not exist ".env" (
    echo SECRET_KEY=finflow_dev_secret_key_change_in_production_32chars > .env
    echo AUDIT_LOG_PATH=%TEMP%\audit_trail.log >> .env
    echo Created .env with default dev keys
)

:: Load .env variables
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
)

python -m uvicorn api.index:app --host 127.0.0.1 --port 8000 --reload

echo.
echo Server stopped.
pause
