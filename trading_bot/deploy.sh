#!/usr/bin/env bash
# deploy.sh
# One-command setup and run script for the Binance Futures Testnet trading bot.
# Idempotent — safe to run multiple times.

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }

# ── Step 1: Check Python 3.10+ ────────────────────────────────────────────────
info "Checking Python version..."

PYTHON_BIN=""
for candidate in python3 python python3.12 python3.11 python3.10; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_BIN="$candidate"
            success "Found Python $version at $(command -v "$candidate")"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    error "Python 3.10 or higher is required but was not found."
    error "Install it from https://www.python.org/downloads/ and re-run this script."
    exit 1
fi

# ── Step 2: Create virtualenv ─────────────────────────────────────────────────
VENV_DIR=".venv"

if [ -d "$VENV_DIR" ]; then
    success "Virtualenv already exists at $VENV_DIR — skipping creation."
else
    info "Creating virtualenv in $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    success "Virtualenv created."
fi

# ── Step 3: Activate virtualenv ───────────────────────────────────────────────
info "Activating virtualenv..."
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
success "Virtualenv activated."

# ── Step 4: Install dependencies ─────────────────────────────────────────────
info "Installing dependencies from requirements.txt..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
success "Dependencies installed."

# ── Step 5: Check / create .env ──────────────────────────────────────────────
if [ -f ".env" ]; then
    success ".env file already exists — skipping."
else
    if [ -f ".env.example" ]; then
        cp .env.example .env
        warn "⚠️  Created .env from template. Fill in your API keys before running."
        warn "    Edit .env and replace the placeholder values with your Binance Testnet credentials."
        warn "    Get testnet keys at: https://testnet.binancefuture.com"
    else
        error ".env.example not found — cannot create .env automatically."
        exit 1
    fi
fi

# ── Step 6: Create logs/ directory ───────────────────────────────────────────
if [ -d "logs" ]; then
    success "logs/ directory already exists."
else
    mkdir -p logs
    success "Created logs/ directory."
fi

# ── Success banner ────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  ✅  Trading Bot setup complete!               ${RESET}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════════════${RESET}"
echo ""
echo -e "${BOLD}Example commands:${RESET}"
echo ""
echo -e "  ${CYAN}# Check server connectivity${RESET}"
echo -e "  python cli.py server-time"
echo ""
echo -e "  ${CYAN}# Place a MARKET BUY order${RESET}"
echo -e "  python cli.py place-order --symbol BTCUSDT --side BUY --order-type MARKET --qty 0.001"
echo ""
echo -e "  ${CYAN}# Place a LIMIT SELL order${RESET}"
echo -e "  python cli.py place-order --symbol BTCUSDT --side SELL --order-type LIMIT --qty 0.001 --price 70000"
echo ""
echo -e "  ${CYAN}# Place a STOP_LIMIT order${RESET}"
echo -e "  python cli.py place-order --symbol BTCUSDT --side SELL --order-type STOP_LIMIT --qty 0.001 --stop-price 59000 --price 58900"
echo ""
echo -e "  ${CYAN}# Enable verbose (DEBUG) logging${RESET}"
echo -e "  python cli.py -v server-time"
echo ""
echo -e "${YELLOW}⚠️  Remember to fill in your API keys in .env before placing orders!${RESET}"
echo ""
