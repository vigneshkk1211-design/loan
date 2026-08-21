#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
#  FinFlow NBFC — Automated Setup & Start Script
#  Works on: Git Bash (Windows), WSL, macOS, Linux
# ════════════════════════════════════════════════════════════════════════
#
#  USAGE:
#    chmod +x run.sh && ./run.sh [command]
#
#  COMMANDS:
#    (none)   — Full setup + start server
#    setup    — Only create venv & install deps
#    start    — Only start Uvicorn (assumes setup already done)
#    test     — Run pytest suite
#    clean    — Remove venv and cache files
# ════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colours ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"

# ── Banner ────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
cat << 'BANNER'
  ╔══════════════════════════════════════════════════════╗
  ║   FinFlow NBFC — CrewAI Agent Platform v1.0         ║
  ║   Accounting · Operations · Compliance Agents       ║
  ╚══════════════════════════════════════════════════════╝
BANNER
echo -e "${RESET}"

# ── Step 1: Verify Python ────────────────────────────────────────────────
setup_check_python() {
  info "Step 1/5 — Checking Python installation…"

  PYTHON_CMD=""
  for cmd in python3 python py; do
    if command -v "$cmd" &>/dev/null; then
      VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
      MAJOR=$(echo "$VER" | cut -d. -f1)
      MINOR=$(echo "$VER" | cut -d. -f2)
      if [[ "$MAJOR" -ge 3 && "$MINOR" -ge 10 ]]; then
        PYTHON_CMD="$cmd"
        success "Found Python $VER at $(command -v $cmd)"
        break
      fi
    fi
  done

  if [[ -z "$PYTHON_CMD" ]]; then
    error "Python 3.10+ is required. Install from https://python.org/downloads/"
  fi
}

# ── Step 2: Create virtual environment ──────────────────────────────────
setup_venv() {
  info "Step 2/5 — Setting up virtual environment…"

  if [[ -d "$VENV_DIR" ]]; then
    warn "Virtual environment already exists at .venv/ — skipping creation"
  else
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    success "Created virtual environment at .venv/"
  fi

  # Activate (Git Bash uses Scripts/, Unix uses bin/)
  if [[ -f "$VENV_DIR/Scripts/activate" ]]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/Scripts/activate"
  else
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
  fi

  success "Virtual environment activated"
  python -m pip install --upgrade pip --quiet
}

# ── Step 3: Install requirements ────────────────────────────────────────
setup_deps() {
  info "Step 3/5 — Installing dependencies from requirements.txt…"

  if [[ ! -f "$SCRIPT_DIR/requirements.txt" ]]; then
    error "requirements.txt not found in $SCRIPT_DIR"
  fi

  pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
  success "All dependencies installed"
}

# ── Step 4: Set up .env ─────────────────────────────────────────────────
setup_env() {
  info "Step 4/5 — Configuring environment variables…"

  if [[ -f "$ENV_FILE" ]]; then
    success ".env already exists — skipping (delete it to regenerate)"
    return
  fi

  if [[ ! -f "$ENV_EXAMPLE" ]]; then
    error ".env.example not found. Cannot create .env."
  fi

  cp "$ENV_EXAMPLE" "$ENV_FILE"

  # Auto-generate a cryptographically random SECRET_KEY
  if command -v python &>/dev/null; then
    GENERATED_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|CHANGE_THIS_TO_A_LONG_RANDOM_SECRET_32_CHARS_MINIMUM|$GENERATED_KEY|g" "$ENV_FILE"
    success "Generated random SECRET_KEY and written to .env"
  fi

  warn "⚠  Review .env and add your OPENAI_API_KEY before starting"
  warn "⚠  NEVER commit .env to version control"
}

# ── Step 5: Start Uvicorn ────────────────────────────────────────────────
start_server() {
  info "Step 5/5 — Starting FastAPI server with Uvicorn…"

  # Load .env into the shell environment
  if [[ -f "$ENV_FILE" ]]; then
    # Export non-comment, non-empty lines
    set -o allexport
    # shellcheck disable=SC1090
    source <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$')
    set +o allexport
    success "Loaded environment from .env"
  fi

  HOST="${HOST:-127.0.0.1}"
  PORT="${PORT:-8000}"

  echo ""
  echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "  🚀  Server starting at  ${CYAN}http://${HOST}:${PORT}${RESET}"
  echo -e "  📖  Swagger UI          ${CYAN}http://${HOST}:${PORT}/docs${RESET}"
  echo -e "  🎯  Dashboard           ${CYAN}http://${HOST}:${PORT}/dashboard${RESET}"
  echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo ""

  cd "$SCRIPT_DIR"
  exec uvicorn api.index:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload \
    --reload-dir api \
    --log-level info
}

# ── Run tests ─────────────────────────────────────────────────────────────
run_tests() {
  info "Running pytest test suite…"

  # Activate venv if not already active
  if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    if [[ -f "$VENV_DIR/Scripts/activate" ]]; then
      source "$VENV_DIR/Scripts/activate"
    elif [[ -f "$VENV_DIR/bin/activate" ]]; then
      source "$VENV_DIR/bin/activate"
    else
      error "Virtual environment not found. Run './run.sh setup' first."
    fi
  fi

  cd "$SCRIPT_DIR"
  python -m pytest tests/ \
    --cov=api/agents \
    --cov-report=term-missing \
    --tb=short \
    -v \
    "$@"
}

# ── Clean up ──────────────────────────────────────────────────────────────
clean_all() {
  warn "Removing .venv/, __pycache__, .pytest_cache, htmlcov…"
  rm -rf "$VENV_DIR" \
         "$SCRIPT_DIR/__pycache__" \
         "$SCRIPT_DIR/.pytest_cache" \
         "$SCRIPT_DIR/htmlcov" \
         "$SCRIPT_DIR/.coverage"
  find "$SCRIPT_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
  find "$SCRIPT_DIR" -name "*.pyc" -delete 2>/dev/null || true
  success "Cleaned up"
}

# ── Command dispatch ──────────────────────────────────────────────────────
CMD="${1:-all}"

case "$CMD" in
  setup)
    setup_check_python
    setup_venv
    setup_deps
    setup_env
    success "Setup complete. Run './run.sh start' to launch the server."
    ;;
  start)
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
      [[ -f "$VENV_DIR/Scripts/activate" ]] && source "$VENV_DIR/Scripts/activate" \
        || source "$VENV_DIR/bin/activate"
    fi
    start_server
    ;;
  test)
    shift || true
    run_tests "$@"
    ;;
  clean)
    clean_all
    ;;
  all|*)
    setup_check_python
    setup_venv
    setup_deps
    setup_env
    start_server
    ;;
esac
