---
name: dca-trading-bot
description: Build a Dollar-Cost Averaging (DCA) trading bot in Python that buys BTC with AUD every Monday on Binance. Use this skill whenever building, extending, or debugging any part of the DCA bot — including backtesting, forward testing, live deployment, scheduling, logging, error handling, or Binance API integration. Always consult this skill before writing any bot code.
---

# DCA Trading Bot — Build Skill

A step-by-step guide for building a weekly AUD/BTC DCA bot on Binance across three phases: backtest → forward test → live.

---

## Project Structure

```
dca-bot/
├── config.yaml           # All runtime parameters (mode, amount, schedule, keys)
├── .env                  # API keys only (never commit this)
├── main.py               # Entry point — reads config, starts scheduler
├── bot/
│   ├── __init__.py
│   ├── config.py         # Loads and validates config + .env
│   ├── exchange.py       # Binance API wrapper (get price, place order, get balance)
│   ├── logger.py         # Structured logging setup
│   ├── database.py       # SQLite trade log (shared schema across all phases)
│   ├── backtest.py       # Phase 1: simulate buys on historical data
│   ├── forward_test.py   # Phase 2: simulate buys on live data, no real orders
│   └── live.py           # Phase 3: place real orders
├── data/
│   └── trades.db         # SQLite database (auto-created)
├── logs/
│   └── bot.log           # Structured log output
└── requirements.txt
```

---

## Config Schema (`config.yaml`)

```yaml
mode: backtest            # Options: backtest | forward_test | live
trading_pair: AUDBTC
buy_amount_aud: 100       # AUD to spend per weekly buy (set when decided)
schedule:
  day: monday
  time: "09:00"           # AEST — converted to UTC internally
backtest:
  start_date: "2021-01-01"
  end_date: "2024-01-01"
  data_source: binance    # Uses Binance historical klines
safety:
  min_balance_aud: 10     # Skip buy and warn if balance falls below this buffer
  max_retries: 3
  retry_delay_seconds: 30
```

`.env` (never committed):
```
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
```

---

## Shared Trade Log Schema (SQLite)

All three phases write to the **same table** so results are directly comparable.

```sql
CREATE TABLE IF NOT EXISTS trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    phase         TEXT NOT NULL,        -- 'backtest' | 'forward_test' | 'live'
    timestamp     TEXT NOT NULL,        -- ISO 8601 UTC
    pair          TEXT NOT NULL,        -- 'AUDBTC'
    price_aud     REAL NOT NULL,        -- BTC price in AUD at time of buy
    aud_spent     REAL NOT NULL,        -- AUD amount spent
    btc_bought    REAL NOT NULL,        -- BTC received (aud_spent / price_aud)
    order_id      TEXT,                 -- NULL for backtest/forward_test
    status        TEXT NOT NULL,        -- 'simulated' | 'filled' | 'skipped' | 'error'
    notes         TEXT                  -- Error messages, skip reasons, etc.
);
```

---

## Error Handling Rules

These rules apply across **all three phases**. Follow them exactly.

### Where to use try-catch

| Location | Risk if unhandled |
|----------|-------------------|
| Order placement (`live.py`) | Exception mid-execution leaves order state unknown — blind retry = double buy |
| Scheduler job wrapper (`main.py`) | Unhandled exception kills the APScheduler job silently — bot appears running but never trades again |
| Binance API calls (price fetch, balance, klines) | Rate limits and network timeouts are common; must catch and recover gracefully |
| Config loading (`config.py`) | Missing key must crash at startup with a clear message, not mid-trade |

### Where NOT to use try-catch

- Pure math (`btc_bought = aud / price`) — if this throws, something is deeply wrong and a hard crash is correct
- SQLite writes — failures are rare; a stack trace is more useful than a swallowed error
- Blanket `except Exception` around entire functions — hides bugs during development

### Exception types (always catch separately)

```python
from binance.exceptions import BinanceAPIException, BinanceRequestException

# BinanceAPIException    — Binance rejected the request (bad params, insufficient funds, invalid pair)
#                          NOT retryable — surface immediately
# BinanceRequestException — Network-level failure (timeout, connection refused)
#                           Retryable — use with_retry() pattern below
```

### Retry pattern (network errors only)

```python
import time

def with_retry(fn, max_retries: int, delay: int, logger):
    """Retry fn up to max_retries times on network errors. Surface API rejections immediately."""
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except BinanceRequestException as e:
            logger.warning(f"Network error on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                time.sleep(delay)
            else:
                raise   # Re-raise after final attempt so caller logs status='error'
        except BinanceAPIException:
            raise       # Not retryable — surface immediately
```

---

## Phase 1 — Backtest

**Goal:** Replay every Monday from `start_date` to `end_date` using Binance historical kline data.

**Steps:**
1. Fetch weekly 1W OHLCV klines for AUDBTC from Binance (`get_historical_klines`)
2. Filter to Mondays only (weekly candle open is always Monday)
3. For each candle: calculate BTC bought = `buy_amount_aud / open_price`
4. Accumulate total AUD spent, total BTC held, running portfolio value
5. Insert each row into `trades` table with `phase = 'backtest'`
6. Print summary table + metrics on completion

**Error handling in this phase:**
- Wrap `get_historical_klines` — rate limits are common on large date ranges
- If klines return empty, exit with a descriptive error rather than producing zero-row output silently

**Output metrics:** total AUD invested, total BTC held, average buy price, portfolio value, ROI%, best/worst single buy

**Phase gate — must pass before forward testing:**
- [ ] All historical Mondays accounted for with no gaps
- [ ] Metrics match manual spot-check of 3 random dates
- [ ] No unhandled exceptions across full date range

---

## Phase 2 — Forward Test

**Goal:** Run the real scheduler against live Binance price data, log simulated trades — no real orders placed.

**Steps:**
1. Scheduler fires every Monday at configured time
2. Fetch live AUDBTC price via `ticker_price()`
3. Calculate BTC that *would* be bought
4. Check simulated AUD balance (starts at a configurable `simulated_balance_aud`)
5. If balance sufficient: log `status = 'simulated'`
6. If balance insufficient: log `status = 'skipped'`, emit warning

**Error handling in this phase:**
- Wrap the entire scheduled job in a top-level catch so a failed price fetch does not kill the scheduler
- On price fetch failure: log `status = 'error'` with the exception message, then return — do not crash

**Phase gate — must pass before going live:**
- [ ] At least 4 consecutive Monday runs logged successfully
- [ ] Kill switch (low balance) triggered and logged in at least one test
- [ ] No missed Monday fires (check scheduler uptime)
- [ ] Developer manually reviews all 4+ trade log entries and signs off

---

## Phase 3 — Live

**Goal:** Place real market buy orders on Binance every Monday.

**Steps:**
1. Scheduler fires every Monday at configured time
2. Fetch real AUD balance from Binance account
3. **Kill switch check:** if balance < `min_balance_aud + buy_amount_aud`, skip + warn
4. **Duplicate check:** if a `live` trade already exists for today's date in DB, skip
5. Place market buy order: `order_market_buy(symbol, quoteOrderQty=buy_amount_aud)`
6. On success: log full order response with `status = 'filled'`
7. On failure: log error, retry up to `max_retries`, then log `status = 'error'`

**Error handling in this phase:**
- `BinanceAPIException` on order = not retryable, log `status = 'error'` immediately
- `BinanceRequestException` on order = retryable via `with_retry()`, log `status = 'error'` after all retries exhausted
- After any network error on order placement: **never assume the order failed** — manually check Binance open orders before next run
- Wrap the full scheduler job in a top-level catch so errors never silently kill the job

**Safety rules (non-negotiable):**
- Mode can only be changed to `live` manually in `config.yaml` — never auto-promoted
- One order per Monday maximum (duplicate guard always runs before placing)
- Real API keys only ever loaded from `.env`, never from `config.yaml`
- All order responses logged in full before any further processing

---

## Key Implementation Rules

| Rule | Detail |
|------|--------|
| Config loading | Validate all required fields on startup; `sys.exit()` with a clear message if missing |
| API errors | Always catch `BinanceAPIException` and `BinanceRequestException` separately |
| Scheduler safety | Wrap every scheduled job in `except Exception` — log and continue, never propagate |
| Retry scope | Only retry `BinanceRequestException` (network). Never retry `BinanceAPIException` (rejected by exchange) |
| Scheduling | Use `APScheduler` `BlockingScheduler` with `CronTrigger(day_of_week='mon')` |
| Timezone | Store all timestamps as UTC in DB; convert to AEST for display only |
| Logging | Use Python `logging` module; write to both stdout and `logs/bot.log` |
| No hardcoding | `buy_amount_aud`, pair, schedule — always from config |
| Mode switching | Only `config.yaml` controls mode; never infer mode from context |

---

## Dependencies (`requirements.txt`)

```
python-binance==1.0.19
apscheduler==3.10.4
python-dotenv==1.0.0
pyyaml==6.0.1
pandas==2.1.0
tabulate==0.9.0
```

---

## Example Implementation

Complete working code for all four core files. Error handling is shown in full — use these as the reference pattern for every phase.

### `bot/config.py`
```python
import os
import sys
import yaml
from dotenv import load_dotenv

load_dotenv()

def load_config(path="config.yaml") -> dict:
    # Config file missing = unrecoverable, crash immediately with a clear message
    try:
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        sys.exit(f"[FATAL] Config file not found: {path}")
    except yaml.YAMLError as e:
        sys.exit(f"[FATAL] Invalid YAML in config file: {e}")

    # Inject API keys from .env
    cfg["api_key"] = os.getenv("BINANCE_API_KEY")
    cfg["api_secret"] = os.getenv("BINANCE_API_SECRET")

    # Validate required fields — fail at startup, not mid-trade
    required = ["mode", "trading_pair", "buy_amount_aud", "api_key", "api_secret"]
    for field in required:
        if not cfg.get(field):
            sys.exit(f"[FATAL] Missing required config field: '{field}'. "
                     f"Check config.yaml and .env.")

    valid_modes = {"backtest", "forward_test", "live"}
    if cfg["mode"] not in valid_modes:
        sys.exit(f"[FATAL] Invalid mode '{cfg['mode']}'. Must be one of: {valid_modes}")

    return cfg
```

### `bot/database.py`
```python
import sqlite3
import logging

DB_PATH = "data/trades.db"
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            phase       TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            pair        TEXT NOT NULL,
            price_aud   REAL NOT NULL,
            aud_spent   REAL NOT NULL,
            btc_bought  REAL NOT NULL,
            order_id    TEXT,
            status      TEXT NOT NULL,
            notes       TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_trade(phase, timestamp, pair, price_aud, aud_spent,
              btc_bought, order_id=None, status="simulated", notes=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO trades
        (phase, timestamp, pair, price_aud, aud_spent, btc_bought, order_id, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (phase, timestamp, pair, price_aud, aud_spent, btc_bought, order_id, status, notes))
    conn.commit()
    conn.close()

def trade_exists_today(phase: str, date_str: str) -> bool:
    """Return True if a trade for this phase already exists on date_str (YYYY-MM-DD)."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("""
        SELECT id FROM trades
        WHERE phase = ? AND timestamp LIKE ?
        LIMIT 1
    """, (phase, f"{date_str}%")).fetchone()
    conn.close()
    return row is not None
```

### `bot/backtest.py`
```python
import logging
from datetime import datetime, timezone
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from tabulate import tabulate
from bot.database import log_trade

logger = logging.getLogger(__name__)

def run_backtest(cfg: dict):
    client = Client(cfg["api_key"], cfg["api_secret"])
    pair = cfg["trading_pair"]
    amount_aud = cfg["buy_amount_aud"]
    start = cfg["backtest"]["start_date"]
    end = cfg["backtest"]["end_date"]

    logger.info(f"Starting backtest | {pair} | {start} → {end} | ${amount_aud} AUD/week")

    # Wrap kline fetch — rate limits are common on large date ranges
    try:
        klines = client.get_historical_klines(
            pair, Client.KLINE_INTERVAL_1WEEK, start, end
        )
    except BinanceAPIException as e:
        logger.error(f"Binance rejected kline request: [{e.status_code}] {e.message}")
        raise
    except BinanceRequestException as e:
        logger.error(f"Network error fetching klines: {e}")
        raise

    if not klines:
        logger.error(
            f"No kline data returned for {pair} between {start} and {end}. "
            "Check the trading pair name and date range."
        )
        return

    total_aud = 0.0
    total_btc = 0.0
    rows = []

    for k in klines:
        open_time = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
        open_price = float(k[1])

        if open_time.weekday() != 0:
            continue

        btc_bought = amount_aud / open_price
        total_aud += amount_aud
        total_btc += btc_bought

        log_trade(
            phase="backtest",
            timestamp=open_time.isoformat(),
            pair=pair,
            price_aud=open_price,
            aud_spent=amount_aud,
            btc_bought=btc_bought,
            status="simulated"
        )

        rows.append([
            open_time.strftime("%Y-%m-%d"),
            f"${open_price:,.2f}",
            f"${amount_aud:.2f}",
            f"{btc_bought:.8f}",
            f"${total_aud:,.2f}",
            f"{total_btc:.8f}"
        ])

    final_price = float(klines[-1][4])
    portfolio_value = total_btc * final_price
    roi = ((portfolio_value - total_aud) / total_aud * 100) if total_aud else 0
    avg_buy_price = total_aud / total_btc if total_btc else 0

    print("\n" + tabulate(rows, headers=[
        "Date", "BTC Price (AUD)", "AUD Spent", "BTC Bought", "Total AUD In", "Total BTC"
    ], tablefmt="rounded_outline"))

    print(f"\n{'='*50}")
    print(f"  Total AUD invested : ${total_aud:,.2f}")
    print(f"  Total BTC held     : {total_btc:.8f} BTC")
    print(f"  Avg buy price      : ${avg_buy_price:,.2f} AUD")
    print(f"  Portfolio value    : ${portfolio_value:,.2f} AUD")
    print(f"  ROI                : {roi:.2f}%")
    print(f"{'='*50}\n")

    logger.info(f"Backtest complete | ROI: {roi:.2f}% | Trades: {len(rows)}")
```

### `bot/live.py`
```python
import time
import logging
from datetime import datetime, timezone
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from bot.database import log_trade, trade_exists_today

logger = logging.getLogger(__name__)

def _place_order(client, pair, amount_aud, max_retries, retry_delay):
    """
    Place a market buy order with retry logic for network errors only.
    - BinanceAPIException (rejected by exchange) → surface immediately, not retried
    - BinanceRequestException (network) → retry up to max_retries times
    Returns the full order response dict on success. Raises on final failure.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return client.order_market_buy(
                symbol=pair,
                quoteOrderQty=amount_aud
            )
        except BinanceAPIException as e:
            logger.error(f"Binance rejected order (not retrying): [{e.status_code}] {e.message}")
            raise
        except BinanceRequestException as e:
            logger.warning(f"Network error on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                logger.error("All retry attempts exhausted.")
                raise

def run_live(cfg: dict):
    client = Client(cfg["api_key"], cfg["api_secret"])
    pair = cfg["trading_pair"]
    amount_aud = cfg["buy_amount_aud"]
    min_balance = cfg["safety"]["min_balance_aud"]
    max_retries = cfg["safety"]["max_retries"]
    retry_delay = cfg["safety"]["retry_delay_seconds"]

    now_utc = datetime.now(tz=timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    ts = now_utc.isoformat()

    logger.info(f"Live buy triggered | {pair} | ${amount_aud} AUD | {today_str}")

    # Duplicate guard — one order per Monday maximum
    if trade_exists_today("live", today_str):
        logger.warning(f"Duplicate guard: live trade already logged for {today_str}. Skipping.")
        return

    # Fetch real AUD balance
    try:
        balance_info = client.get_asset_balance(asset="AUD")
        balance_aud = float(balance_info["free"])
    except BinanceAPIException as e:
        msg = f"Balance fetch rejected by Binance: {e.message}"
        logger.error(msg)
        log_trade("live", ts, pair, 0, 0, 0, status="error", notes=msg)
        return
    except BinanceRequestException as e:
        msg = f"Network error fetching balance: {e}"
        logger.error(msg)
        log_trade("live", ts, pair, 0, 0, 0, status="error", notes=msg)
        return

    # Kill switch
    required = amount_aud + min_balance
    if balance_aud < required:
        msg = (f"Balance too low: ${balance_aud:.2f} AUD available, "
               f"${required:.2f} required (buy + buffer). Skipping.")
        logger.warning(msg)
        log_trade("live", ts, pair, 0, amount_aud, 0, status="skipped", notes=msg)
        return

    # Fetch current price for logging (non-critical — order proceeds even if this fails)
    price_aud = 0.0
    try:
        ticker = client.get_symbol_ticker(symbol=pair)
        price_aud = float(ticker["price"])
    except (BinanceAPIException, BinanceRequestException) as e:
        logger.warning(f"Could not fetch price for logging: {e}. Proceeding with order.")

    # Place the order
    try:
        order = _place_order(client, pair, amount_aud, max_retries, retry_delay)
        btc_bought = float(order.get("executedQty", 0))
        order_id = str(order.get("orderId", ""))

        logger.info(f"Order filled | ID: {order_id} | {btc_bought:.8f} BTC | ${amount_aud:.2f} AUD")
        log_trade(
            phase="live",
            timestamp=ts,
            pair=pair,
            price_aud=price_aud,
            aud_spent=amount_aud,
            btc_bought=btc_bought,
            order_id=order_id,
            status="filled"
        )

    except BinanceAPIException as e:
        msg = f"Order rejected by Binance: [{e.status_code}] {e.message}"
        logger.error(msg)
        log_trade("live", ts, pair, price_aud, amount_aud, 0, status="error", notes=msg)

    except BinanceRequestException as e:
        msg = f"Network error — order state unknown after {max_retries} retries: {e}"
        logger.error(msg)
        log_trade("live", ts, pair, price_aud, amount_aud, 0, status="error", notes=msg)
        # WARNING: Manually check Binance open orders before the next scheduled run
```

### `main.py`
```python
import logging
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from bot.config import load_config
from bot.database import init_db

os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def make_job(cfg: dict):
    """
    Returns the scheduled job for the configured mode, wrapped in a top-level
    except block. This is critical: if the job raises and is not caught here,
    APScheduler removes it silently — the bot appears running but never trades again.
    """
    mode = cfg["mode"]

    if mode == "forward_test":
        from bot.forward_test import run_forward_test
        fn = lambda: run_forward_test(cfg)
    elif mode == "live":
        from bot.live import run_live
        fn = lambda: run_live(cfg)
    else:
        raise ValueError(f"make_job called with non-schedulable mode: {mode}")

    def safe_job():
        try:
            fn()
        except Exception as e:
            # Log the full traceback but keep the scheduler alive for next Monday
            logger.error(f"Scheduled job failed: {e}", exc_info=True)
            logger.info("Scheduler still running — next Monday fire is preserved.")

    return safe_job

if __name__ == "__main__":
    cfg = load_config()
    init_db()

    mode = cfg["mode"]
    logger.info(f"DCA Bot starting in mode: {mode.upper()}")

    if mode == "backtest":
        from bot.backtest import run_backtest
        run_backtest(cfg)

    elif mode in ("forward_test", "live"):
        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(
            make_job(cfg),
            CronTrigger(day_of_week="mon", hour=23, minute=0)  # 09:00 AEST = 23:00 UTC
        )
        logger.info("Scheduler started. Waiting for Monday 09:00 AEST...")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot shut down by user.")

    else:
        logger.error(f"Unknown mode in config: '{mode}'")
```

---

## How to Use This Skill

1. **Always build one phase at a time.** Complete and verify backtest before writing forward_test code.
2. **Use the shared DB schema from day one.** All three phases must write identical columns.
3. **Never hardcode values.** Every parameter flows from `config.yaml` or `.env`.
4. **Follow the error handling rules exactly.** The only acceptable top-level `except Exception` is in the scheduler job wrapper in `main.py`.
5. **Check the phase gate checklist** before advancing. Do not skip it.
6. **After any `BinanceRequestException` on a live order**, manually verify open orders on Binance before the next scheduled run.
7. **When in doubt about a Binance endpoint**, check the `python-binance` docs at https://python-binance.readthedocs.io/
