"""
bot/backtest.py — Phase 1: Historical DCA simulation.

Fetches weekly AUDBTC klines from Binance, simulates a Monday buy for
every candle, logs each trade to SQLite, and prints a summary table
with key portfolio metrics on completion.

Error handling (per skill rules):
  - kline fetch wrapped: BinanceAPIException is not retried;
    BinanceRequestException raises so main.py can handle it.
  - Empty kline response exits with a descriptive error.
  - Pure math (btc = aud / price) is NOT wrapped — a crash here
    means something is deeply wrong and a traceback is more useful.

Usage:
    from bot.backtest import run_backtest
    run_backtest(cfg)
"""

import logging
from datetime import datetime, timezone

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from tabulate import tabulate

from bot.database import log_trade

logger = logging.getLogger(__name__)


def run_backtest(cfg: dict) -> None:
    """
    Execute the full backtest simulation.

    For every weekly kline candle in the configured date range whose
    open_time falls on a Monday, simulates purchasing buy_amount_aud
    of BTC at the candle's open price. Logs each simulated trade to
    the shared SQLite trades table, then prints a summary.

    Args:
        cfg: Validated config dict from bot.config.load_config().
             Required keys: api_key, api_secret, trading_pair,
             buy_amount_aud, backtest.start_date, backtest.end_date.
    """
    client = Client(cfg["api_key"], cfg["api_secret"])
    pair = cfg["trading_pair"]
    amount_aud = cfg["buy_amount_aud"]
    start = cfg["backtest"]["start_date"]
    end = cfg["backtest"]["end_date"]

    logger.info(
        "Starting backtest | %s | %s -> %s | $%.2f AUD/week",
        pair, start, end, amount_aud,
    )

    # ------------------------------------------------------------------
    # Fetch historical klines — wrap per skill error handling rules.
    # BinanceAPIException = exchange rejected request (bad pair, bad
    #   dates) — not retryable, log and re-raise immediately.
    # BinanceRequestException = network failure — re-raise so the
    #   caller can decide to retry; do not silently swallow it.
    # ------------------------------------------------------------------
    try:
        klines = client.get_historical_klines(
            pair,
            Client.KLINE_INTERVAL_1WEEK,
            start,
            end,
        )
    except BinanceAPIException as e:
        logger.error(
            "Binance rejected kline request: [%s] %s", e.status_code, e.message
        )
        raise
    except BinanceRequestException as e:
        logger.error("Network error fetching klines: %s", e)
        raise

    # Empty response = wrong pair name or date range before listing
    if not klines:
        logger.error(
            "No kline data returned for %s between %s and %s. "
            "Check the trading_pair and backtest dates in config.yaml. "
            "Note: AUDBTC may not have been listed on Binance before 2021.",
            pair, start, end,
        )
        return

    logger.info("Fetched %d weekly candles. Simulating Monday buys...", len(klines))

    # ------------------------------------------------------------------
    # Simulation loop
    # ------------------------------------------------------------------
    total_aud = 0.0
    total_btc = 0.0
    best_buy: dict = {}    # lowest price paid
    worst_buy: dict = {}   # highest price paid
    rows = []              # for tabulate display

    for k in klines:
        # kline fields: [open_time, open, high, low, close, volume, ...]
        open_time = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
        open_price = float(k[1])

        # Weekly 1W candles from Binance always open on Monday UTC.
        # This guard is a safety net for any edge-case data irregularity.
        if open_time.weekday() != 0:
            logger.warning(
                "Skipping non-Monday candle: %s (weekday=%d)",
                open_time.date(), open_time.weekday(),
            )
            continue

        # Core DCA math — intentionally unwrapped (see module docstring)
        btc_bought = amount_aud / open_price
        total_aud += amount_aud
        total_btc += btc_bought

        ts = open_time.isoformat()

        # Persist to shared SQLite schema
        log_trade(
            phase="backtest",
            timestamp=ts,
            pair=pair,
            price_aud=open_price,
            aud_spent=amount_aud,
            btc_bought=btc_bought,
            status="simulated",
        )

        # Track best and worst single buy for metrics display
        if not best_buy or open_price < best_buy["price"]:
            best_buy = {"date": open_time.strftime("%Y-%m-%d"), "price": open_price}
        if not worst_buy or open_price > worst_buy["price"]:
            worst_buy = {"date": open_time.strftime("%Y-%m-%d"), "price": open_price}

        rows.append([
            open_time.strftime("%Y-%m-%d"),
            f"${open_price:,.2f}",
            f"${amount_aud:.2f}",
            f"{btc_bought:.8f}",
            f"${total_aud:,.2f}",
            f"{total_btc:.8f}",
        ])

    if not rows:
        logger.error(
            "Klines were returned but no Monday candles found. "
            "This is unexpected — check Binance kline interval alignment."
        )
        return

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    # Use the first candle's open price and final candle's close price
    first_price = float(klines[0][1])
    final_price = float(klines[-1][4])
    
    portfolio_value = total_btc * final_price
    roi = ((portfolio_value - total_aud) / total_aud * 100) if total_aud else 0
    market_roi = ((final_price - first_price) / first_price * 100) if first_price else 0
    avg_buy_price = total_aud / total_btc if total_btc else 0

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    print("\n" + tabulate(
        rows,
        headers=["Date", "BTC Price (AUD)", "AUD Spent", "BTC Bought", "Total AUD In", "Total BTC"],
        tablefmt="psql",
    ))

    print(f"\n{'='*55}")
    print(f"  DCA BACKTEST RESULTS {pair}")
    print(f"{'='*55}")
    print(f"  Trades simulated   : {len(rows)}")
    print(f"  Total AUD invested : ${total_aud:,.2f}")
    print(f"  Total BTC held     : {total_btc:.8f} BTC")
    print(f"  Avg buy price      : ${avg_buy_price:,.2f} AUD/BTC")
    print(f"  Current BTC price  : ${final_price:,.2f} AUD/BTC (last candle close)")
    print(f"  Portfolio value    : ${portfolio_value:,.2f} AUD")
    print(f"  DCA Bot ROI        : {roi:+.2f}%")
    print(f"  Market BTC ROI     : {market_roi:+.2f}%")
    if best_buy:
        print(f"  Best buy           : ${best_buy['price']:,.2f} on {best_buy['date']}")
    if worst_buy:
        print(f"  Worst buy          : ${worst_buy['price']:,.2f} on {worst_buy['date']}")
    print(f"{'='*55}\n")

    logger.info(
        "Backtest complete | Trades: %d | ROI: %.2f%% | "
        "Total AUD: $%.2f | Total BTC: %.8f",
        len(rows), roi, total_aud, total_btc,
    )
