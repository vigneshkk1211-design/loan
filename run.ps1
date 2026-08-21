<#
.SYNOPSIS
    FinFlow NBFC — Automated Setup & Start Script (PowerShell)

.DESCRIPTION
    Sets up a Python virtual environment, installs dependencies,
    configures .env, and starts the FastAPI server using Uvicorn.
    Compatible with Windows PowerShell 5.1+ and PowerShell 7+.

.PARAMETER Command
    all    — Full setup + start server (default)
    setup  — Only create venv & install deps
    start  — Only start Uvicorn (assumes setup done)
    test   — Run pytest suite
    clean  — Remove venv and cache files

.EXAMPLE
    .\run.ps1
    .\run.ps1 setup
    .\run.ps1 test
    .\run.ps1 clean
#>

param(
    [ValidateSet('all','setup','start','test','clean')]
    [string]$Command = 'all',
    [string[]]$TestArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Helpers ──────────────────────────────────────────────────────────────
function Write-Info    { param($m) Write-Host "[INFO]  $m" -ForegroundColor Cyan }
function Write-OK      { param($m) Write-Host "[OK]    $m" -ForegroundColor Green }
function Write-Warn    { param($m) Write-Host "[WARN]  $m" -ForegroundColor Yellow }
function Write-Fail    { param($m) Write-Host "[ERROR] $m" -ForegroundColor Red; exit 1 }

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir    = Join-Path $ScriptDir ".venv"
$EnvFile    = Join-Path $ScriptDir ".env"
$EnvExample = Join-Path $ScriptDir ".env.example"

# ── Banner ────────────────────────────────────────────────────────────────
Write-Host @"

  ╔══════════════════════════════════════════════════════╗
  ║   FinFlow NBFC — CrewAI Agent Platform v1.0         ║
  ║   Accounting · Operations · Compliance Agents       ║
  ╚══════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

# ── Step 1: Verify Python ────────────────────────────────────────────────
function Step-CheckPython {
    Write-Info "Step 1/5 — Checking Python installation…"

    $pythonCmd = $null
    foreach ($cmd in @('python', 'python3', 'py')) {
        try {
            $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($ver) {
                $parts = $ver.Split('.')
                if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                    $pythonCmd = $cmd
                    Write-OK "Found Python $ver"
                    break
                }
            }
        } catch { }
    }

    if (-not $pythonCmd) {
        Write-Fail "Python 3.10+ is required. Install from: https://python.org/downloads/"
    }
    return $pythonCmd
}

# ── Step 2: Create virtual environment ──────────────────────────────────
function Step-CreateVenv {
    param([string]$PythonCmd)
    Write-Info "Step 2/5 — Setting up virtual environment…"

    if (Test-Path $VenvDir) {
        Write-Warn "Virtual environment already exists at .venv\ — skipping"
    } else {
        & $PythonCmd -m venv $VenvDir
        Write-OK "Created virtual environment at .venv\"
    }

    # Activate
    $activateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
    if (Test-Path $activateScript) {
        & $activateScript
        Write-OK "Virtual environment activated"
    } else {
        Write-Fail "Could not find activation script at: $activateScript"
    }

    python -m pip install --upgrade pip --quiet
}

# ── Step 3: Install requirements ─────────────────────────────────────────
function Step-InstallDeps {
    Write-Info "Step 3/5 — Installing dependencies from requirements.txt…"

    $reqFile = Join-Path $ScriptDir "requirements.txt"
    if (-not (Test-Path $reqFile)) {
        Write-Fail "requirements.txt not found at: $reqFile"
    }

    pip install -r $reqFile --quiet
    Write-OK "All dependencies installed"
}

# ── Step 4: Set up .env ──────────────────────────────────────────────────
function Step-SetupEnv {
    Write-Info "Step 4/5 — Configuring environment variables…"

    if (Test-Path $EnvFile) {
        Write-OK ".env already exists — skipping (delete it to regenerate)"
        return
    }

    if (-not (Test-Path $EnvExample)) {
        Write-Fail ".env.example not found. Cannot create .env."
    }

    Copy-Item $EnvExample $EnvFile

    # Auto-generate SECRET_KEY
    $secretKey = python -c "import secrets; print(secrets.token_hex(32))"
    $content = Get-Content $EnvFile -Raw
    $content = $content -replace 'CHANGE_THIS_TO_A_LONG_RANDOM_SECRET_32_CHARS_MINIMUM', $secretKey
    Set-Content $EnvFile $content -Encoding UTF8
    Write-OK "Generated random SECRET_KEY and written to .env"

    Write-Warn "Review .env and add your OPENAI_API_KEY before starting"
    Write-Warn "NEVER commit .env to version control"
}

# ── Load .env file ────────────────────────────────────────────────────────
function Load-EnvFile {
    if (Test-Path $EnvFile) {
        Get-Content $EnvFile | Where-Object {
            $_ -notmatch '^\s*#' -and $_ -notmatch '^\s*$'
        } | ForEach-Object {
            $parts = $_ -split '=', 2
            if ($parts.Length -eq 2) {
                $key   = $parts[0].Trim()
                $value = $parts[1].Trim().Trim('"').Trim("'")
                [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
            }
        }
        Write-OK "Loaded environment from .env"
    }
}

# ── Step 5: Start Uvicorn ────────────────────────────────────────────────
function Step-StartServer {
    Write-Info "Step 5/5 — Starting FastAPI server with Uvicorn…"
    Load-EnvFile

    $host = if ($env:HOST) { $env:HOST } else { '127.0.0.1' }
    $port = if ($env:PORT) { $env:PORT } else { '8000' }

    Write-Host ""
    Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
    Write-Host "  🚀  Server:      http://${host}:${port}" -ForegroundColor White
    Write-Host "  📖  Swagger UI:  http://${host}:${port}/docs" -ForegroundColor White
    Write-Host "  🎯  Dashboard:   http://${host}:${port}/dashboard" -ForegroundColor White
    Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
    Write-Host ""

    Set-Location $ScriptDir
    uvicorn api.index:app `
        --host $host `
        --port $port `
        --reload `
        --reload-dir api `
        --log-level info
}

# ── Run tests ─────────────────────────────────────────────────────────────
function Run-Tests {
    Write-Info "Running pytest test suite…"
    Load-EnvFile
    Set-Location $ScriptDir

    $env:SECRET_KEY = if ($env:SECRET_KEY) { $env:SECRET_KEY } else { 'TEST_SECRET_KEY_FOR_PYTEST_ONLY' }

    python -m pytest tests/ `
        --cov=api/agents `
        --cov-report=term-missing `
        --tb=short `
        -v `
        @TestArgs
}

# ── Clean up ──────────────────────────────────────────────────────────────
function Clean-All {
    Write-Warn "Removing .venv\, __pycache__, .pytest_cache, .coverage…"
    foreach ($path in @($VenvDir, '.pytest_cache', 'htmlcov', '.coverage')) {
        $full = Join-Path $ScriptDir $path
        if (Test-Path $full) { Remove-Item $full -Recurse -Force }
    }
    Get-ChildItem $ScriptDir -Recurse -Filter '__pycache__' -Directory |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem $ScriptDir -Recurse -Filter '*.pyc' |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Write-OK "Cleaned up"
}

# ── Command dispatch ──────────────────────────────────────────────────────
switch ($Command) {
    'setup' {
        $py = Step-CheckPython
        Step-CreateVenv -PythonCmd $py
        Step-InstallDeps
        Step-SetupEnv
        Write-OK "Setup complete. Run '.\run.ps1 start' to launch the server."
    }
    'start' {
        $activateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
        if (Test-Path $activateScript) { & $activateScript }
        Step-StartServer
    }
    'test' {
        $activateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
        if (Test-Path $activateScript) { & $activateScript }
        Run-Tests
    }
    'clean' {
        Clean-All
    }
    default {
        $py = Step-CheckPython
        Step-CreateVenv -PythonCmd $py
        Step-InstallDeps
        Step-SetupEnv
        Step-StartServer
    }
}
