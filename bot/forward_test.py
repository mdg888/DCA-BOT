"""
bot/forward_test.py — Phase 2: Live paper trading simulation.

Runs on the live APScheduler in main.py. Connects to the real Binance
ticker for current pricing, but simulates the buy against a mock AUD
balance. Does not place any real orders.

Usage: Called natively by main.py when mode="forward_test".
"""

import logging
from datetime import datetime, timezone

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

from bot.database import log_trade

logger = logging.getLogger(__name__)


def run_forward_test(cfg: dict) -> None:
    """
    Execute a simulated live trade against current market data.

    Called by the scheduler every Monday. Fetches the live ticker price,
    checks if the simulated balance is sufficient, and logs the result
    to SQLite as if it were a real trade.

    Args:
        cfg: Validated config dict.
    """
    client = Client(cfg["api_key"], cfg["api_secret"])
    pair = cfg["trading_pair"]
    amount_aud = cfg["buy_amount_aud"]
    
    # Used for mock balance tracking in forward_test
    # (Live mode fetches the real wallet balance from Binance)
    sim_balance = cfg["forward_test"].get("simulated_balance_aud", 1000.0)
    
    now_utc = datetime.now(tz=timezone.utc)
    ts = now_utc.isoformat()
    
    logger.info(
        "Forward test triggered | %s | $%.2f AUD | Simulated Balance: $%.2f",
        pair, amount_aud, sim_balance,
    )

    # ------------------------------------------------------------------
    # 1. Fetch live price
    # Wraps networking completely — if it fails, log as error and return
    # rather than crashing the scheduler job.
    # ------------------------------------------------------------------
    try:
        ticker = client.get_symbol_ticker(symbol=pair)
        price_aud = float(ticker["price"])
    except BinanceAPIException as e:
        msg = f"Binance rejected price request: [{e.status_code}] {e.message}"
        logger.error(msg)
        log_trade("forward_test", ts, pair, 0, 0, 0, status="error", notes=msg)
        return
    except BinanceRequestException as e:
        msg = f"Network error fetching live price: {e}"
        logger.error(msg)
        log_trade("forward_test", ts, pair, 0, 0, 0, status="error", notes=msg)
        return

    # ------------------------------------------------------------------
    # 2. Check mock balance (kill-switch simulation)
    # ------------------------------------------------------------------
    # The safety buffer ensures we don't buy if fiat gets too low
    min_balance = cfg["safety"]["min_balance_aud"]
    required_balance = amount_aud + min_balance

    if sim_balance < required_balance:
        msg = (
            f"Simulated balance too low: ${sim_balance:.2f} available, "
            f"${required_balance:.2f} required (buy + safety buffer)."
        )
        logger.warning(msg)
        log_trade(
            phase="forward_test",
            timestamp=ts,
            pair=pair,
            price_aud=price_aud,
            aud_spent=amount_aud,
            btc_bought=0.0,
            status="skipped",
            notes=msg
        )
        return

    # ------------------------------------------------------------------
    # 3. Simulate Buy
    # ------------------------------------------------------------------
    btc_bought = amount_aud / price_aud
    
    log_trade(
        phase="forward_test",
        timestamp=ts,
        pair=pair,
        price_aud=price_aud,
        aud_spent=amount_aud,
        btc_bought=btc_bought,
        status="simulated",
        notes=None
    )
    
    logger.info(
        "Forward test trade simulated | Bought %.8f BTC @ $%.2f AUD",
        btc_bought, price_aud
    )
