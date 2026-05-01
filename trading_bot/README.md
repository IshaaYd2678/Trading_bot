# Binance Futures Testnet Trading Bot

## 1. Overview

A production-ready Python CLI trading bot that places **Market**, **Limit**, and **Stop-Limit** orders on the [Binance USDT-M Futures Testnet](https://testnet.binancefuture.com). Built with `httpx` for direct REST communication, `Typer` + `Rich` for a polished CLI experience, `Pydantic v2` for strict input validation, and a dual-handler logging system that writes full DEBUG traces to disk while keeping the terminal clean.

---

## 2. Prerequisites

| Requirement | Details |
|---|---|
| **Python** | 3.10 or higher |
| **Binance Testnet account** | Register at [testnet.binancefuture.com](https://testnet.binancefuture.com) and generate API keys under *API Management* |
| **pip** | Comes with Python; used to install dependencies |

> **Note:** This bot targets the **Futures Testnet** only. It will not work against the live Binance API without changing `BASE_URL` in `bot/client.py`.

---

## 3. Quick Start (using deploy.sh)

```bash
# 1. Clone / download the project
cd trading_bot

# 2. Run the one-command setup script
bash deploy.sh

# 3. Fill in your testnet API credentials
#    (deploy.sh creates .env from .env.example automatically)
nano .env          # or use any text editor

# 4. Verify connectivity
python cli.py server-time

# 5. Place your first order
python cli.py place-order --symbol BTCUSDT --side BUY --type MARKET --qty 0.001
```

---

## 4. Manual Setup (without deploy.sh)

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
# Edit .env and add your testnet API key and secret

# Create the logs directory
mkdir -p logs
```

---

## 5. Configuration

Copy `.env.example` to `.env` and replace the placeholder values:

```dotenv
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here
```

Keys are loaded at startup via `python-dotenv`. They are **never** hardcoded in source files and are **never** echoed to the terminal or committed to version control.

Get testnet credentials at: https://testnet.binancefuture.com → *API Management*

---

## 6. Usage Examples

### Check server time (verify connectivity)
```bash
python cli.py server-time
```

### Place a MARKET BUY order
```bash
python cli.py place-order \
  --symbol BTCUSDT \
  --side BUY \
  --order-type MARKET \
  --qty 0.001
```

### Place a LIMIT SELL order
```bash
python cli.py place-order \
  --symbol ETHUSDT \
  --side SELL \
  --order-type LIMIT \
  --qty 0.05 \
  --price 3250.00
```

### Place a STOP_LIMIT order
```bash
python cli.py place-order \
  --symbol BTCUSDT \
  --side SELL \
  --order-type STOP_LIMIT \
  --qty 0.001 \
  --stop-price 59000 \
  --price 58900
```

### Enable verbose (DEBUG) logging
```bash
python cli.py -v server-time
python cli.py --verbose place-order --symbol BTCUSDT --side BUY --order-type MARKET --qty 0.001
```

### Get help
```bash
python cli.py --help
python cli.py place-order --help
```

---

## 7. Project Structure

```
trading_bot/
├── bot/
│   ├── __init__.py          # Package exports (BinanceClient, OrderManager, etc.)
│   ├── client.py            # Binance REST client — httpx, HMAC signing, error handling
│   ├── orders.py            # Order placement logic — OrderManager, OrderResult dataclass
│   ├── validators.py        # Pydantic v2 input validation — OrderInput model
│   └── logging_config.py   # Dual-handler logging setup (file + Rich terminal)
├── cli.py                   # Typer CLI entry point — place-order, server-time commands
├── .env                     # Your API credentials (not committed to git)
├── .env.example             # Credential template
├── requirements.txt         # Pinned Python dependencies
├── deploy.sh                # One-command idempotent setup script
├── README.md                # This file
└── logs/
    ├── .gitkeep             # Keeps the directory in version control
    ├── trading_bot.log      # Runtime log (auto-created, DEBUG level)
    ├── sample_market_order.log   # Example MARKET order log output
    └── sample_limit_order.log    # Example LIMIT order log output
```

---

## 8. Error Handling

| Error scenario | Behaviour |
|---|---|
| Missing / placeholder API keys | Friendly message printed to stderr; exit code 1. No stack trace shown. |
| Invalid order parameters (bad symbol, missing price, etc.) | Pydantic `ValidationError` caught; each field error printed clearly; exit code 1. |
| Binance API error (e.g. `-2015 Invalid API key`) | `BinanceAPIError` caught; human-readable message shown; full traceback written to log file only. |
| Network timeout (> 10 s) | `httpx.TimeoutException` wrapped in `BinanceAPIError`; clear message shown. |
| Network unreachable | `httpx.NetworkError` wrapped in `BinanceAPIError`; clear message shown. |
| Unexpected exceptions | Caught at CLI level; message shown without stack trace; exit code 1. |

Stack traces are always written to `logs/trading_bot.log` at ERROR level for post-mortem debugging, but are never displayed to the user on the terminal.

---

## 9. Logging

| Handler | Destination | Level | Format |
|---|---|---|---|
| `FileHandler` | `logs/trading_bot.log` | DEBUG | `timestamp \| LEVEL \| logger \| message` |
| `RichHandler` | Terminal (stdout) | INFO (or DEBUG with `-v`) | Coloured Rich output |

Every outgoing HTTP request (method, URL, params) is logged at **DEBUG**.  
Every HTTP response (status code, body) is logged at **DEBUG**.  
Order summaries and results are logged at **INFO**.  
Errors with full tracebacks are logged at **ERROR** (file only).

`httpx` and `httpcore` internal logs are suppressed to **WARNING** to avoid noise.

---

## 10. Assumptions & Limitations

- **Testnet only.** The base URL is hardcoded to `https://testnet.binancefuture.com`. To use against live Binance, change `BASE_URL` in `bot/client.py` and exercise extreme caution.
- **USDT-M Futures only.** Symbol validation enforces a `USDT` or `BUSD` suffix. Coin-M (delivery) contracts are not supported.
- **No position management.** The bot places orders but does not track open positions, PnL, or account balance.
- **No order book / price feed.** Prices must be supplied by the user. There is no market data integration.
- **Single order per invocation.** The CLI is designed for one order per run. Batch ordering would require scripting multiple calls.
- **GTC time-in-force.** All limit orders use `timeInForce=GTC`. IOC/FOK are not exposed via the CLI.
- **Quantity precision.** Binance enforces symbol-specific lot size and tick size rules. If an order is rejected for precision reasons, adjust your `--qty` or `--price` to match the symbol's filters (visible via `GET /fapi/v1/exchangeInfo`).
- **Clock skew.** Binance rejects requests with a timestamp more than 1000 ms from server time. The bot uses `time.time()` which relies on your system clock being accurate. Run `python cli.py server-time` to verify synchronisation.
