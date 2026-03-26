# DCA Bot — Agent Reference (AGENT.md)

This file is the single source of truth for any AI agent or developer working on this codebase.
It documents architecture, file responsibilities, conventions, and phase-gate rules.

---

## 1. Project Overview

A **Dollar-Cost Averaging (DCA) trading bot** that buys a fixed AUD amount of Bitcoin (BTC)
every Monday on Binance. Built in Python, controlled entirely via a `.env` config file.

| Item | Value |
|------|-------|
| Trading pair | `AUDBTC` (buy BTC with AUD) |
| Exchange | Binance (REST API) |
| Schedule | Every Monday at a configurable time (default 09:00 AEST) |
| Language | Python 3.10+ |
| Framework | None (standalone scripts) |
| Config | `.env` file (loaded by `python-dotenv`) |
| Scheduling | `APScheduler` (in-process, not OS cron) |
| Trade storage | SQLite (`data/trades.db`) |
| Logging | Structured `key=value` logs to file + stdout |

---

## 2. Project Layout

```
DCA-BOT/
├── .ai/
│   ├── PRD/
│   │   └── PRD.md          ← Full Product Requirements Document
│   └── AGENT.md            ← This file
├── data/
│   ├── trades.db           ← SQLite trade log (auto-created)
│   └── AUDBTC_historical.csv ← Cached Binance OHLCV data (auto-created)
├── logs/
│   └── dca_bot.log         ← Rotating log file (auto-created)
├── output/
│   └── equity_curve.png    ← Backtest equity chart (auto-created)
├── config.py               ← Config loader + validator
├── logger.py               ← Structured logging setup
├── trade_log.py            ← SQLite schema + read/write helpers
├── binance_client.py       ← Binance REST API wrapper
├── backtest.py             ← Phase 1: historical simulation engine
├── forward_test.py         ← Phase 2: paper trading engine
├── live_trade.py           ← Phase 3: real order placement
├── scheduler.py            ← APScheduler + Monday guard + kill switch
├── main.py                 ← Entry point; reads MODE and routes to correct engine
├── .env                    ← Runtime config (NEVER commit — in .gitignore)
├── .env.example            ← Template with all keys documented
└── requirements.txt        ← Pinned Python dependencies
```

---

## 3. Configuration (.env)

All runtime parameters live in `.env`. The bot validates every required key at startup.

### Full Parameter Reference

| Key | Type | Default | Required | Description |
|-----|------|---------|----------|-------------|
| `MODE` | str | `backtest` | Yes | `backtest` / `forward_test` / `live` |
| `TRADING_PAIR` | str | `AUDBTC` | Yes | Binance symbol |
| `AUD_AMOUNT` | float | — | Yes | Fixed AUD to spend each Monday — **must be set** |
| `SCHEDULE_DAY` | str | `monday` | Yes | Day for weekly buy (keep as `monday`) |
| `SCHEDULE_TIME` | str | `09:00` | Yes | 24h AEST time, e.g. `09:00` |
| `TIMEZONE` | str | `Australia/Sydney` | Yes | pytz timezone string |
| `API_KEY` | str | — | live only | Binance API key |
| `API_SECRET` | str | — | live only | Binance API secret |
| `BACKTEST_START_DATE` | str | `2019-01-07` | backtest | ISO 8601 start date |
| `BACKTEST_END_DATE` | str | today | backtest | ISO 8601 end date (empty = today) |
| `HISTORICAL_DATA_CACHE` | str | `data/AUDBTC_historical.csv` | backtest | OHLCV cache path |
| `EQUITY_CURVE_OUTPUT` | str | `output/equity_curve.png` | backtest | Chart output path |
| `DATABASE_PATH` | str | `data/trades.db` | Yes | SQLite file path |
| `LOG_LEVEL` | str | `INFO` | Yes | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FILE` | str | `logs/dca_bot.log` | Yes | Log file path |
| `MAX_RETRIES` | int | `3` | Yes | Retry attempts for price fetches |
| `RETRY_BACKOFF_SECONDS` | int | `5` | Yes | Base seconds for exponential backoff |
| `MAX_PRICE_AUD_BTC` | float | `0` | No | Price sanity ceiling (0 = disabled) |
| `MIN_BALANCE_BUFFER_PCT` | float | `1.0` | live | Extra % buffer over AUD_AMOUNT required |
| `RECVWINDOW_MS` | int | `5000` | live | Binance recvWindow in ms |
| `VERSION` | str | `1.0.0` | Yes | Logged at startup |

---

## 4. File Responsibilities

### `config.py`
- Loads `.env` with `python-dotenv`
- Validates all required keys; raises `ValueError` with a clear message if missing
- Returns a typed `Config` dataclass
- **Never** passes `API_KEY` / `API_SECRET` to logging

### `logger.py`
- Configures a single `logging.Logger` instance with:
  - `StreamHandler` (stdout)
  - `TimedRotatingFileHandler` (daily rotation)
- All log records use `key=value` format: `ts=<iso> level=INFO event=trade_executed phase=backtest ...`

### `trade_log.py`
- Creates and migrates the SQLite database at import time
- Tables: `trades`, `system_events` (see schema below)
- Functions: `insert_trade()`, `get_trades()`, `trade_exists_for_monday()`, `insert_event()`
- Uses WAL mode for crash safety

### `binance_client.py`
- Wraps `python-binance` (`Client`)
- Public methods (no auth): `get_current_price()`, `get_klines()`, `get_exchange_info()`
- Private methods (auth required): `get_aud_balance()`, `place_market_buy()`
- **Never** logs `API_KEY` or `API_SECRET`
- Enforces rate limiting: minimum 1 second between consecutive calls

### `backtest.py`
- Fetches/loads historical OHLCV data (with local CSV cache)
- Iterates over all Mondays in the configured date range
- Simulates a buy at each Monday's open price
- Logs each simulated trade to SQLite with `phase='backtest'`
- Prints a summary table + key metrics to stdout
- Saves equity curve PNG

### `forward_test.py`
- Runs inside the APScheduler job on Monday
- Fetches live spot price from Binance public API
- Logs a simulated trade (no real order) with `phase='forward_test'`
- Prints running portfolio summary after each execution

### `live_trade.py`
- Runs inside the APScheduler job on Monday
- Pre-checks: Monday guard, duplicate check, balance check
- Places authenticated market buy via `POST /api/v3/order`
- Records Binance order ID, fill price, quantity, commission
- **Never retries** a market order on failure

### `scheduler.py`
- Configures `BackgroundScheduler` (APScheduler)
- Wraps the job with: kill switch check → Monday guard → engine call
- Missed job policy: `misfire_grace_time=60`, `coalesce=True` (never catch up)

### `main.py`
- Reads `MODE` from config
- In `backtest` mode: calls `run_backtest()` and exits
- In `forward_test` / `live` mode: starts scheduler and blocks

---

## 5. SQLite Schema

### `trades` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `phase` | TEXT | `backtest` / `forward_test` / `live` |
| `trade_date` | TEXT | Monday date `YYYY-MM-DD` |
| `executed_at` | TEXT | ISO 8601 with timezone |
| `symbol` | TEXT | Always `AUDBTC` |
| `aud_amount` | REAL | AUD spent |
| `price_aud_btc` | REAL | Fill/simulated price |
| `btc_quantity` | REAL | BTC received |
| `cumulative_btc` | REAL | Running BTC total (this phase) |
| `cumulative_aud_invested` | REAL | Running AUD total (this phase) |
| `order_id` | TEXT | NULL for simulated |
| `commission` | REAL | NULL for simulated |
| `status` | TEXT | `success` / `skipped` / `error` |
| `notes` | TEXT | Error details, skip reason |
| `created_at` | TEXT | Record insertion time |

### `system_events` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `event_type` | TEXT | `startup` / `shutdown` / `error` / `kill_switch` |
| `phase` | TEXT | Active mode |
| `message` | TEXT | Human-readable description |
| `occurred_at` | TEXT | ISO 8601 datetime |

---

## 6. Phase Gate Rules

### Gate 1: Backtest → Forward Test
The developer must manually verify before changing `MODE=forward_test`:
- Backtest ran clean, no exceptions
- Trade log has one entry per Monday (minus known data gaps)
- Equity curve PNG generated and looks correct (staircase pattern)
- Spot-check: 3 random rows → `aud_amount / price_aud_btc ≈ btc_quantity` (within 0.01%)
- No duplicate Monday entries

### Gate 2: Forward Test → Live
The developer must manually verify before changing `MODE=live`:
- Bot has run without crashing for **4 consecutive Mondays**
- All 4 records in SQLite with correct timestamps and prices
- Kill switch tested (placing `KILL_SWITCH` file → graceful shutdown)
- Monday guard tested (non-Monday trigger was skipped)
- Balance check + duplicate prevention unit-tested or manually verified
- `API_KEY` / `API_SECRET` confirmed absent from all log files

---

## 7. Safety Rules (Hard Constraints)

1. **Never advance MODE automatically** — developer must edit `.env` manually
2. **Never retry a live market order** — ambiguous fills risk double-buys
3. **Never buy on non-Monday** — Monday guard enforced by scheduler job wrapper
4. **Never log API credentials** — scrub from all exceptions and log records
5. **Never place a partial buy** — if balance < `AUD_AMOUNT`, skip and log a warning
6. **Kill switch** — if file `KILL_SWITCH` exists in working dir, shutdown immediately
7. **Backtest uses only public Binance endpoints** — no auth in backtest mode

---

## 8. Key Assumptions & Decisions

| # | Assumption | Rationale |
|---|-----------|-----------|
| A1 | `quoteOrderQty` used for live orders (spend fixed AUD) | Correct for DCA; avoids rounding issues with BTC quantity |
| A2 | Backtest uses daily (`1d`) candles filtered to Mondays | More accurate than weekly (`1w`) candles whose open time may not align to Monday |
| A3 | Missed Monday (bot offline) is skipped — no catch-up | DCA consistency > make-up trades; avoids multi-buy catch-up risk |
| A4 | `python-binance` library used over `ccxt` | Binance-native, simpler for single-exchange use |
| A5 | Equity curve uses weekly Close price for portfolio value | Closing price is a standard portfolio valuation point |
| A6 | `KILL_SWITCH` is a file (not an env var) so it can be dropped without restarting the bot | File-based kill switch works even if env vars are not reloadable at runtime |

---

## 9. Development Checklist

### Phase 1 — Backtest
- [ ] `config.py` written and validated
- [ ] `logger.py` written
- [ ] `trade_log.py` written (schema + helpers)
- [ ] `binance_client.py` written (public endpoints only)
- [ ] `backtest.py` written
- [ ] `main.py` written
- [ ] `.env.example` written
- [ ] `requirements.txt` written
- [ ] Backtest runs successfully end-to-end
- [ ] Gate 1 criteria satisfied

### Phase 2 — Forward Test
- [ ] `forward_test.py` written
- [ ] `scheduler.py` written (APScheduler + Monday guard)
- [ ] `main.py` updated for scheduler mode
- [ ] 4-Monday forward test completed
- [ ] Gate 2 criteria satisfied

### Phase 3 — Live
- [ ] `live_trade.py` written
- [ ] `binance_client.py` extended with private endpoints
- [ ] `main.py` updated for live mode
- [ ] First successful real order placed and logged

---

## 10. Open Questions

| # | Question | Status |
|---|----------|--------|
| OQ-01 | **What is the weekly AUD_AMOUNT?** | ❓ Not yet decided — set in `.env` before running |
| OQ-02 | What infrastructure hosts the live bot? | ❓ Open (VPS recommended for reliability) |
| OQ-03 | Should missed Monday runs ever be caught up? | ❓ Current default: no catch-up (see A3) |

---

*Last updated: 2026-03-26 — Phase 1 build*
