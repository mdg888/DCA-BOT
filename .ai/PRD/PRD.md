# Product Requirements Document (PRD)
# Dollar-Cost Averaging (DCA) Trading Bot — AUD/BTC on Binance

**Version:** 1.0  
**Date:** 2026-03-26  
**Author:** Solo Developer  
**Status:** Draft — Pending Open Question Resolution

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Goals & Success Metrics](#2-goals--success-metrics)
3. [User Stories](#3-user-stories)
4. [Functional Requirements](#4-functional-requirements)
5. [Non-Functional Requirements](#5-non-functional-requirements)
6. [System Architecture](#6-system-architecture)
7. [Data Requirements](#7-data-requirements)
8. [API Integration Details](#8-api-integration-details)
9. [Risk & Safety Controls](#9-risk--safety-controls)
10. [Configuration Reference](#10-configuration-reference)
11. [Phase Gate Criteria](#11-phase-gate-criteria)
12. [Out of Scope](#12-out-of-scope)
13. [Open Questions](#13-open-questions)

---

## 1. Executive Summary

This document defines requirements for a Python-based Dollar-Cost Averaging (DCA) trading bot that automatically purchases Bitcoin (BTC) with Australian Dollars (AUD) on Binance at a fixed weekly cadence. The bot is designed for a solo developer running it on their own infrastructure and will be built and validated across three sequential phases: **Backtesting**, **Forward Testing (Paper Trading)**, and **Live Deployment**.

The system will be a single standalone Python script (or small module) with no web framework dependency. All parameters — including the weekly purchase amount, API credentials, schedule time, and operational mode — are externalised to a configuration file. The bot must never advance to a later phase until explicit phase gate criteria have been satisfied.

---

## 2. Goals & Success Metrics

### 2.1 Primary Goals

| # | Goal |
|---|------|
| G1 | Automate weekly BTC purchases without manual intervention |
| G2 | Validate strategy performance through backtesting before risking real capital |
| G3 | Confirm live infrastructure reliability through forward testing |
| G4 | Provide clear, auditable logs of every trade event and system state |
| G5 | Allow all key parameters to be changed without touching source code |

### 2.2 Success Metrics

| Phase | Metric | Target |
|-------|--------|--------|
| Backtest | Historical simulation completes without errors | 100% run success |
| Backtest | ROI% and equity curve outputs are produced | Both present in output |
| Backtest | Simulated P&L matches manual spot-check calculation | ≤ 0.01% deviation |
| Forward Test | Bot runs for ≥ 4 consecutive Mondays without crashes | 4/4 executions logged |
| Forward Test | All simulated trades are logged with correct timestamp & price | 100% log completeness |
| Live | First real order executes successfully within 60 seconds of scheduled time | Time delta ≤ 60s |
| Live | No duplicate orders are placed in a single Monday window | 0 duplicates |
| Live | All errors trigger structured log entries and do not crash the process | 100% error capture |

---

## 3. User Stories

| ID | As a… | I want to… | So that… |
|----|--------|------------|---------|
| US-01 | Developer | Run the bot in backtest mode against historical AUD/BTC data | I can verify the DCA strategy's historical performance before using real money |
| US-02 | Developer | Switch between backtest, forward test, and live modes via a single config flag | I never accidentally run in the wrong mode |
| US-03 | Developer | Configure the weekly AUD purchase amount in a config file | I can change the amount without editing source code |
| US-04 | Developer | Set the execution time and day via config | I can adjust the schedule without rewriting the scheduler |
| US-05 | Developer | View an equity curve chart from the backtest | I can visually inspect the DCA strategy performance over time |
| US-06 | Developer | Read structured logs for every trade event | I can audit what the bot did and diagnose problems |
| US-07 | Developer | Have the bot check for sufficient AUD balance before placing any live order | I am protected against failed orders due to insufficient funds |
| US-08 | Developer | Use a kill switch to halt the bot immediately | I can stop operation without killing the OS process manually |
| US-09 | Developer | Prevent duplicate orders within the same Monday window | I am protected against scheduler double-fires or restarts causing double buys |
| US-10 | Developer | See a summary table of total invested, total BTC held, average buy price, and ROI% | I can track overall portfolio performance at a glance |

---

## 4. Functional Requirements

### 4.1 General / All Modes

| ID | Requirement |
|----|-------------|
| FR-GEN-01 | The bot MUST read all runtime parameters from a single `.env` or `config.yaml` file at startup |
| FR-GEN-02 | The bot MUST validate all required config values on startup and exit with a clear error message if any are missing or malformed |
| FR-GEN-03 | The `MODE` config parameter MUST control which operational mode runs: `backtest`, `forward_test`, or `live` |
| FR-GEN-04 | The scheduler MUST be implemented using `APScheduler` or `schedule` (not OS cron) and MUST run entirely within the Python process |
| FR-GEN-05 | All trade records MUST be persisted to SQLite (preferred) or CSV for auditability |
| FR-GEN-06 | The bot MUST produce structured log output (JSON-formatted or key=value) for every trade event, error, and mode transition |
| FR-GEN-07 | The bot MUST enforce Monday-only execution — any accidental trigger on another day MUST be logged as a warning and skipped |
| FR-GEN-08 | The trading pair MUST be `AUDBTC` on Binance |

---

### 4.2 Phase 1 — Backtesting

| ID | Requirement |
|----|-------------|
| FR-BT-01 | The backtest engine MUST fetch historical OHLCV (Open/High/Low/Close/Volume) data for `AUDBTC` from a configurable start date to a configurable end date |
| FR-BT-02 | Historical data MUST be sourced from the Binance REST API (`GET /api/v3/klines`) using weekly (`1w`) or daily (`1d`) candles, or from a local CSV cache if present |
| FR-BT-03 | The backtester MUST simulate a buy order on every Monday within the date range, using the weekly open price as the simulated fill price |
| FR-BT-04 | The backtester MUST calculate and output the following metrics: total AUD invested, total BTC accumulated, average purchase price (AUD/BTC), current portfolio value (AUD), and ROI% |
| FR-BT-05 | The backtester MUST produce an equity curve plot (portfolio value in AUD over time) saved as a PNG file to a configurable output directory |
| FR-BT-06 | The backtester MUST log each simulated trade with: date, simulated price (AUD/BTC), AUD spent, BTC received, and cumulative BTC held |
| FR-BT-07 | Backtest results MUST be written to the trade log storage (SQLite/CSV) under a distinct `phase = backtest` column/tag |
| FR-BT-08 | If no historical data is available for a given Monday (e.g., exchange holiday or data gap), the bot MUST skip that week and log a warning |
| FR-BT-09 | The backtest MUST NOT make any real API authenticated calls — it MAY use public unauthenticated endpoints only |
| FR-BT-10 | The backtester MUST handle the scenario where the configured AUD amount is larger than the smallest lot size for the pair and round down to the nearest valid quantity |

---

### 4.3 Phase 2 — Forward Testing (Paper Trading)

| ID | Requirement |
|----|-------------|
| FR-FT-01 | In `forward_test` mode the bot MUST connect to the live Binance public market data feed to fetch the current `AUDBTC` price at execution time |
| FR-FT-02 | The bot MUST simulate a buy at the current market price WITHOUT placing a real order (no authenticated order endpoints may be called) |
| FR-FT-03 | The simulated trade MUST be logged with: timestamp (AEST), simulated market price, AUD amount, BTC quantity (AUD ÷ price), and cumulative BTC held |
| FR-FT-04 | The bot MUST track a running paper portfolio: total AUD invested, total simulated BTC held, current portfolio value, and unrealised ROI% |
| FR-FT-05 | The scheduler MUST fire at the configured day and time (default: Monday 09:00 AEST) and execute if and only if today is Monday |
| FR-FT-06 | In `forward_test` mode the bot MUST check that the current price fetch succeeds before logging a trade; on failure it MUST retry up to `MAX_RETRIES` times with exponential backoff before logging an error and skipping the week |
| FR-FT-07 | A summary report MUST be printable on demand (e.g., via a `--report` CLI flag) showing the full trade history and portfolio summary |
| FR-FT-08 | The forward test MUST run for at least 4 consecutive scheduled Mondays before the phase gate is considered satisfiable |

---

### 4.4 Phase 3 — Live Deployment

| ID | Requirement |
|----|-------------|
| FR-LV-01 | In `live` mode the bot MUST authenticate to the Binance REST API using the configured `API_KEY` and `API_SECRET` |
| FR-LV-02 | The bot MUST place a **market buy** order for `AUDBTC` with the configured AUD quote quantity (`quoteOrderQty`) |
| FR-LV-03 | Before placing any order the bot MUST query the account's free AUD balance and abort (log error, skip week) if the balance is less than the configured purchase amount |
| FR-LV-04 | The bot MUST check the trade log for an existing successful order on the current Monday before placing a new order; if one exists it MUST skip and log a warning (duplicate order prevention) |
| FR-LV-05 | After a successful order the bot MUST record the order ID, executed quantity, average fill price, commission, and timestamp in the trade log |
| FR-LV-06 | The bot MUST implement a kill switch: reading a file `KILL_SWITCH` in the working directory — if present, all scheduled executions MUST be aborted and the process MUST exit gracefully |
| FR-LV-07 | On any Binance API error (HTTP 4xx or 5xx) the bot MUST: log the error with status code and response body, NOT retry a market order (to avoid accidental double-fills), and skip the week |
| FR-LV-08 | The bot MUST log a structured entry at process start containing: mode, version, configured schedule, and all non-secret config values |
| FR-LV-09 | API keys MUST NOT appear in any log output, file, or exception traceback |
| FR-LV-10 | The bot MUST enforce that live orders are placed ONLY on Mondays; any execution trigger on a non-Monday day MUST be caught, logged as a critical warning, and skipped |

---

## 5. Non-Functional Requirements

### 5.1 Security

| ID | Requirement |
|----|-------------|
| NFR-SEC-01 | `API_KEY` and `API_SECRET` MUST be stored only in `.env` (never committed to version control); `.env` MUST be listed in `.gitignore` |
| NFR-SEC-02 | API keys MUST be loaded into memory only and never written to logs, databases, or stdout |
| NFR-SEC-03 | The Binance API key used for live trading SHOULD be scoped to `Enable Trading` only; withdrawal permissions MUST NOT be enabled |
| NFR-SEC-04 | All Binance API calls MUST use HTTPS |
| NFR-SEC-05 | The trade log database file SHOULD have filesystem permissions restricted to the owning user |

### 5.2 Reliability

| ID | Requirement |
|----|-------------|
| NFR-REL-01 | The bot process MUST recover from transient network errors without crashing (retry with backoff for price fetches; skip-and-log for order placement) |
| NFR-REL-02 | The scheduler MUST be configured with a missed-job policy: if the scheduled job was missed (e.g., process was down), it MUST NOT fire a catch-up run — the week is simply skipped |
| NFR-REL-03 | The SQLite trade log database MUST use WAL (Write-Ahead Logging) mode to prevent corruption on unexpected termination |
| NFR-REL-04 | The bot MUST be runnable as a long-lived process (days/weeks) without memory leaks |

### 5.3 Performance

| ID | Requirement |
|----|-------------|
| NFR-PERF-01 | The backtest for 5 years of weekly data MUST complete in under 60 seconds on a standard developer machine |
| NFR-PERF-02 | Live order placement (from scheduler trigger to API call) MUST complete within 30 seconds |
| NFR-PERF-03 | The bot MUST NOT poll the Binance API more frequently than once per 5 seconds during price fetches to respect rate limits |

### 5.4 Maintainability

| ID | Requirement |
|----|-------------|
| NFR-MAINT-01 | All configuration MUST be externalised; changing any parameter MUST require only a config file edit and process restart |
| NFR-MAINT-02 | Source code MUST pass `flake8` linting with no errors |
| NFR-MAINT-03 | All functions performing I/O or API calls MUST have docstrings describing inputs, outputs, and side effects |
| NFR-MAINT-04 | A `requirements.txt` MUST be provided and pinned to specific versions |

---

## 6. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      DCA Bot Process                        │
│                                                             │
│  ┌──────────────┐    ┌───────────────┐   ┌──────────────┐  │
│  │  Config      │    │   Scheduler   │   │  Kill Switch │  │
│  │  Loader      │───▶│  (APScheduler)│   │  Watcher     │  │
│  │  (.env /     │    │               │   │  (file check)│  │
│  │  config.yaml)│    └──────┬────────┘   └──────┬───────┘  │
│  └──────────────┘           │                   │          │
│                             │ Monday trigger     │ ABORT    │
│                             ▼                   │          │
│                    ┌────────────────┐            │          │
│                    │  Mode Router   │◀───────────┘          │
│                    │  (backtest /   │                       │
│                    │  forward_test /│                       │
│                    │  live)         │                       │
│                    └───────┬────────┘                       │
│             ┌──────────────┼───────────────┐               │
│             ▼              ▼               ▼               │
│    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐     │
│    │  Backtest    │ │  Forward     │ │  Live        │     │
│    │  Engine      │ │  Test Engine │ │  Trade Engine│     │
│    │              │ │              │ │              │     │
│    │ - Fetch OHLCV│ │ - Fetch spot │ │ - Pre-checks │     │
│    │ - Simulate   │ │   price      │ │ - Balance    │     │
│    │   weekly buys│ │ - Simulate   │ │   check      │     │
│    │ - Calc metrics│ │   trade log  │ │ - Dedup check│     │
│    │ - Plot curve │ │ - Portfolio  │ │ - Market buy │     │
│    └──────┬───────┘ │   summary    │ │ - Record fill│     │
│           │         └──────┬───────┘ └──────┬───────┘     │
│           └────────────────┼────────────────┘             │
│                            ▼                               │
│                   ┌─────────────────┐                      │
│                   │   Trade Logger  │                      │
│                   │   (SQLite/CSV)  │                      │
│                   │   + Structured  │                      │
│                   │   Log Output    │                      │
│                   └─────────────────┘                      │
│                                                             │
│                   ┌─────────────────┐                      │
│                   │  Binance API    │                      │
│                   │  Client         │                      │
│                   │  (python-binance│                      │
│                   │   or ccxt)      │                      │
│                   └─────────────────┘                      │
└─────────────────────────────────────────────────────────────┘

External:
  ┌──────────────────────┐
  │   Binance REST API   │
  │   api.binance.com    │
  │   - Public endpoints │
  │     (klines, ticker) │
  │   - Private endpoints│
  │     (order, balance) │
  └──────────────────────┘
```

### 6.1 Module Structure (Suggested)

```
dca_bot/
├── main.py              # Entry point; config load, mode routing, scheduler start
├── config.py            # Config loader and validator
├── scheduler.py         # APScheduler setup, Monday-only guard, kill switch check
├── backtest.py          # Backtesting engine and equity curve plotter
├── forward_test.py      # Paper trading engine
├── live_trade.py        # Live order placement engine
├── binance_client.py    # Binance API wrapper (price fetch, order, balance)
├── trade_log.py         # SQLite/CSV persistence layer
├── logger.py            # Structured logging setup
├── requirements.txt
├── config.yaml          # (or .env) — all runtime parameters
└── .ai/
    └── PRD/
        └── PRD.md       # This document
```

---

## 7. Data Requirements

### 7.1 Historical Data (Backtesting)

- **Source:** Binance public REST API — `GET /api/v3/klines`
- **Symbol:** `AUDBTC`
- **Interval:** `1w` (weekly) or `1d` (daily, filtered to Mondays)
- **Fields used:** Open time, Open price, Close price
- **Caching:** Fetched data MUST be cached to a local CSV file (`data/AUDBTC_historical.csv`) to avoid re-fetching on every backtest run
- **Cache invalidation:** Cache is considered stale if the most recent candle's close time is more than 7 days in the past
- **Date range:** Configurable via `BACKTEST_START_DATE` and `BACKTEST_END_DATE` in config

### 7.2 Trade Log Schema (SQLite)

**Table: `trades`**

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Internal record ID |
| `phase` | TEXT NOT NULL | `backtest`, `forward_test`, or `live` |
| `trade_date` | TEXT NOT NULL | ISO 8601 date of the Monday (YYYY-MM-DD) |
| `executed_at` | TEXT NOT NULL | ISO 8601 datetime with timezone (AEST) |
| `symbol` | TEXT NOT NULL | Always `AUDBTC` |
| `aud_amount` | REAL NOT NULL | AUD amount spent (configured purchase amount) |
| `price_aud_btc` | REAL NOT NULL | Fill/simulated price (AUD per BTC) |
| `btc_quantity` | REAL NOT NULL | BTC quantity received (aud_amount ÷ price) |
| `cumulative_btc` | REAL NOT NULL | Running total BTC accumulated in this phase |
| `cumulative_aud_invested` | REAL NOT NULL | Running total AUD invested in this phase |
| `order_id` | TEXT | Binance order ID (live only; NULL for simulated) |
| `commission` | REAL | Commission paid in BTC (live only; NULL otherwise) |
| `status` | TEXT NOT NULL | `success`, `skipped`, `error` |
| `notes` | TEXT | Free-text notes, error messages, skip reasons |
| `created_at` | TEXT NOT NULL | Record insertion timestamp |

**Table: `system_events`**

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Internal record ID |
| `event_type` | TEXT NOT NULL | `startup`, `shutdown`, `mode_switch`, `kill_switch`, `error` |
| `phase` | TEXT NOT NULL | Active phase at time of event |
| `message` | TEXT NOT NULL | Human-readable event description |
| `occurred_at` | TEXT NOT NULL | ISO 8601 datetime |

---

## 8. API Integration Details

### 8.1 Binance Endpoints Used

| Endpoint | Method | Auth | Used In | Purpose |
|----------|--------|------|---------|---------|
| `GET /api/v3/ping` | Public | None | All modes | Connectivity check on startup |
| `GET /api/v3/time` | Public | None | All modes | Server time sync |
| `GET /api/v3/klines` | Public | None | Backtest | Historical OHLCV data |
| `GET /api/v3/ticker/price` | Public | None | Forward Test, Live | Current spot price for AUDBTC |
| `GET /api/v3/exchangeInfo` | Public | None | All modes | Lot size and minimum order filters |
| `GET /api/v3/account` | Private | HMAC-SHA256 | Live | AUD free balance check |
| `POST /api/v3/order` | Private | HMAC-SHA256 | Live | Place market buy order |
| `GET /api/v3/order` | Private | HMAC-SHA256 | Live | Verify order fill details |

### 8.2 Authentication Method

All private endpoints use **HMAC-SHA256** request signing per the [Binance API documentation](https://binance-docs.github.io/apidocs/spot/en/):

1. All parameters (including `timestamp` and `recvWindow`) are concatenated as a query string
2. The string is signed with `API_SECRET` using HMAC-SHA256
3. The `signature` parameter is appended to the request
4. `X-MBX-APIKEY` header is set to `API_KEY`

### 8.3 Order Parameters (Live Market Buy)

```json
{
  "symbol": "AUDBTC",
  "side": "BUY",
  "type": "MARKET",
  "quoteOrderQty": "<configured_aud_amount>",
  "timestamp": "<current_unix_ms>",
  "recvWindow": 5000
}
```

> **Note:** Using `quoteOrderQty` (spend exactly X AUD) rather than `quantity` (buy exactly X BTC) is the correct approach for a DCA strategy spending a fixed fiat amount.

### 8.4 Rate Limits

| Limit Type | Limit | Handling |
|------------|-------|----------|
| Request Weight | 1200/min | Bot makes ≤ 5 requests per scheduled execution — well within limits |
| Order Rate | 10 orders/sec, 100,000 orders/24h | 1 order per week — not a concern |
| IP bans | Triggered by repeated 429 responses | Bot MUST honour `Retry-After` header and back off accordingly |

### 8.5 Exchange Info Validation (Symbol Filters)

Before each buy (backtest and live), the bot MUST validate the order against these Binance `AUDBTC` filters fetched from `/api/v3/exchangeInfo`:

- **`MIN_NOTIONAL`**: Configured AUD amount must be ≥ minimum notional. Bot aborts if violated.
- **`LOT_SIZE`**: BTC quantity must conform to `stepSize`. Apply `math.floor` to the raw quantity divided by `stepSize`, then multiply back.
- **`PRICE_FILTER`**: Not applicable for market orders.

---

## 9. Risk & Safety Controls

| Control | Description |
|---------|-------------|
| **Mode Gate** | `live` mode requires an explicit `MODE=live` config value; `forward_test` and `backtest` are the default safe modes |
| **Monday-Only Guard** | The scheduler job checks `datetime.now(AEST).weekday() == 0` before any execution. Any non-Monday trigger is logged as `CRITICAL` and skipped |
| **Kill Switch** | A file named `KILL_SWITCH` in the working directory is polled before every scheduled execution. If present, the process calls `scheduler.shutdown()` and exits with code 0 |
| **Minimum Balance Check** | Before placing a live order, the bot queries `GET /api/v3/account` and compares `free` AUD against the configured amount plus a 1% buffer. Aborts if insufficient |
| **Duplicate Order Prevention** | Before placing a live order, the bot queries the `trades` table for a `success` record with `phase=live` and `trade_date = today's Monday`. If found, execution is skipped and a warning is logged |
| **No Market Order Retry** | If a live `POST /api/v3/order` call fails, the bot MUST NOT retry it. The week is skipped. This prevents accidental double-buys from network timeout ambiguity |
| **No Withdrawal Permissions** | The Binance API key MUST NOT have withdrawal permissions enabled. This is enforced by documentation requirement (NFR-SEC-03); the bot cannot programmatically enforce this |
| **recvWindow Cap** | `recvWindow` is capped at 5000ms to minimise the window in which a delayed request could be accepted by the exchange |
| **Price Sanity Check** | Before any simulated or live buy, the fetched price is compared against a configurable `MAX_PRICE_AUD_BTC` threshold. If the price exceeds this value, the order is aborted and an alert is logged (protects against erroneous price data) |
| **Backtest-Only API Calls** | Backtest mode MUST use only public, unauthenticated endpoints. A startup check asserts that `API_KEY` and `API_SECRET` are not read from config in backtest mode |

---

## 10. Configuration Reference

All parameters are defined in `config.yaml` (or `.env`). The bot validates all of these at startup.

### 10.1 Full Parameter Table

| Parameter | Type | Default | Required | Description |
|-----------|------|---------|----------|-------------|
| `MODE` | string | `backtest` | Yes | Operational mode: `backtest`, `forward_test`, or `live` |
| `TRADING_PAIR` | string | `AUDBTC` | Yes | Binance trading symbol (do not change) |
| `AUD_AMOUNT` | float | *(see Open Questions)* | Yes | Fixed AUD amount to spend per weekly DCA buy |
| `SCHEDULE_DAY` | string | `monday` | Yes | Day of week to execute (must remain `monday`) |
| `SCHEDULE_TIME` | string | `09:00` | Yes | 24h time in AEST for scheduled execution, e.g. `09:00` |
| `TIMEZONE` | string | `Australia/Sydney` | Yes | Timezone for schedule interpretation |
| `API_KEY` | string | — | Live only | Binance API key (not used in backtest/forward_test) |
| `API_SECRET` | string | — | Live only | Binance API secret (not used in backtest/forward_test) |
| `BACKTEST_START_DATE` | string | `2019-01-07` | Backtest | Start date for historical simulation (ISO 8601) |
| `BACKTEST_END_DATE` | string | today | Backtest | End date for historical simulation (ISO 8601) |
| `HISTORICAL_DATA_CACHE` | string | `data/AUDBTC_historical.csv` | Backtest | Path to local OHLCV cache file |
| `EQUITY_CURVE_OUTPUT` | string | `output/equity_curve.png` | Backtest | Path to save equity curve PNG |
| `DATABASE_PATH` | string | `data/trades.db` | Yes | Path to SQLite trade log database |
| `LOG_LEVEL` | string | `INFO` | Yes | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | string | `logs/dca_bot.log` | Yes | Path to log file (rotated daily) |
| `MAX_RETRIES` | integer | `3` | Yes | Max retries for price fetch on network failure |
| `RETRY_BACKOFF_SECONDS` | integer | `5` | Yes | Base seconds for exponential backoff between retries |
| `MAX_PRICE_AUD_BTC` | float | `0` (disabled) | No | Price sanity check ceiling; `0` disables the check |
| `MIN_BALANCE_BUFFER_PCT` | float | `1.0` | Live | Extra % buffer above AUD_AMOUNT required in account |
| `RECVWINDOW_MS` | integer | `5000` | Live | Binance recvWindow in milliseconds (max 60000) |
| `VERSION` | string | `1.0.0` | Yes | Bot version string logged at startup |

### 10.2 Sample `config.yaml`

```yaml
# DCA Bot Configuration
MODE: backtest            # backtest | forward_test | live

TRADING_PAIR: AUDBTC
AUD_AMOUNT: 100.00        # ⚠ TO BE DECIDED — see Open Questions

SCHEDULE_DAY: monday
SCHEDULE_TIME: "09:00"
TIMEZONE: Australia/Sydney

# API Credentials (live mode only — keep in .env, not here)
# API_KEY: your_key_here
# API_SECRET: your_secret_here

BACKTEST_START_DATE: "2019-01-07"
BACKTEST_END_DATE: ""     # empty = today
HISTORICAL_DATA_CACHE: data/AUDBTC_historical.csv
EQUITY_CURVE_OUTPUT: output/equity_curve.png

DATABASE_PATH: data/trades.db
LOG_LEVEL: INFO
LOG_FILE: logs/dca_bot.log

MAX_RETRIES: 3
RETRY_BACKOFF_SECONDS: 5
MAX_PRICE_AUD_BTC: 0      # 0 = disabled

MIN_BALANCE_BUFFER_PCT: 1.0
RECVWINDOW_MS: 5000

VERSION: "1.0.0"
```

> **Security Note:** `API_KEY` and `API_SECRET` MUST be stored in a `.env` file (not `config.yaml`) and loaded via `python-dotenv`. The `.env` file MUST be in `.gitignore`.

---

## 11. Phase Gate Criteria

Advancement between phases is **manual and deliberate**. The developer MUST verify each gate before changing `MODE` in config.

### 11.1 Gate 1: Backtest → Forward Test

All of the following must be satisfied:

- [ ] Backtest completes without Python exceptions for the full configured date range
- [ ] Trade log contains one simulated buy record for every Monday in the date range (minus any data-gap skips)
- [ ] Metrics output includes: total AUD invested, total BTC accumulated, average buy price, final portfolio value (AUD), ROI%
- [ ] Equity curve PNG is generated and visually inspected — shows a recognisable DCA staircase pattern
- [ ] At least one spot-check manual calculation (pick 3 random weeks, verify aud_amount ÷ price = btc_quantity) passes with ≤ 0.01% deviation
- [ ] No duplicate Monday entries exist in the trade log
- [ ] All backtest log output is structured and parseable
- [ ] The bot correctly skips weeks with missing OHLCV data

### 11.2 Gate 2: Forward Test → Live

All of the following must be satisfied:

- [ ] Bot has run in `forward_test` mode for a minimum of **4 consecutive Mondays** without crashing
- [ ] All 4 scheduled executions fired within ±60 seconds of the configured time
- [ ] Trade log contains 4 complete forward-test records with correct timestamps, prices, and quantities
- [ ] Portfolio summary report generates correctly and totals match the log records
- [ ] Kill switch was tested: placing `KILL_SWITCH` file caused graceful shutdown and no further executions occurred
- [ ] API connectivity check passes (public endpoints reachable)
- [ ] Monday-only guard was tested: manually triggering on a non-Monday logged a warning and skipped
- [ ] All forward test log output is structured and complete
- [ ] AUD balance check logic was validated (manually or via unit test)
- [ ] Duplicate order prevention logic was validated (manually or via unit test)
- [ ] `API_KEY` and `API_SECRET` are confirmed absent from all log files produced during forward test

---

## 12. Out of Scope

The following are explicitly **not** included in this version:

| Item | Rationale |
|------|-----------|
| Web dashboard or UI | Bot is a standalone script; no web framework |
| Mobile notifications (push/SMS/email) | Not required for V1 |
| Dynamic DCA strategies (e.g. value averaging, crash buying) | Fixed weekly amount only |
| Multiple trading pairs | AUD/BTC only |
| Binance WebSocket / streaming data | REST API polling is sufficient for weekly frequency |
| Automated phase advancement | Advancing between phases is a manual developer action |
| Portfolio rebalancing or selling | Buy-only DCA strategy |
| Tax reporting | Out of scope; use trade log as raw data source for external tools |
| CI/CD pipeline | Solo developer workflow; manual deployment |
| Containerisation (Docker) | Not required for V1 |
| Multiple exchange support | Binance only |
| Stop-loss or take-profit orders | Pure DCA — no exit strategy |

---

## 13. Open Questions

| # | Question | Impact | Owner | Status |
|---|----------|--------|-------|--------|
| OQ-01 | **What is the weekly AUD purchase amount?** The `AUD_AMOUNT` config parameter is the most financially significant value and has not been decided. Candidates might be $50, $100, $200, or $250 AUD per week. This value must be confirmed before live deployment. | High — directly determines capital exposure and portfolio growth rate | Developer | ❓ Open |
| OQ-02 | **Should `config.yaml` and `.env` coexist, or use one file?** Using `.env` alone is simpler for secrets but less structured. Using `config.yaml` for non-secrets and `.env` for keys is more maintainable. | Low — implementation detail | Developer | ❓ Open |
| OQ-03 | **Should the backtest use weekly (`1w`) candles using the Monday open price, or daily (`1d`) candles filtered to Mondays?** Daily candles give more precise Monday-specific prices; weekly candles may not align to Monday opens exactly on Binance. | Medium — affects backtest accuracy | Developer | ❓ Open |
| OQ-04 | **What is the preferred Python library: `python-binance` or `ccxt`?** `python-binance` is Binance-native and simpler; `ccxt` is multi-exchange and more abstracted. Given Binance-only scope, `python-binance` is likely preferred. | Low — implementation detail | Developer | ❓ Open |
| OQ-05 | **What infrastructure will host the live bot?** Options include a local machine (unreliable for uptime), a VPS (reliable), or a Raspberry Pi. The Monday 09:00 AEST schedule requires the host to be reliably online at that time. | Medium — affects reliability of live phase | Developer | ❓ Open |
| OQ-06 | **Should missed scheduled runs (bot was offline on a Monday) trigger a catch-up execution?** The current NFR-REL-02 says no catch-up. This should be explicitly confirmed as intentional. | Medium — affects DCA consistency if the bot has downtime | Developer | ❓ Open |

---

*End of Document — Version 1.0 — 2026-03-26*
