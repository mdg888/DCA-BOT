"""
bot/live.py — Phase 3: Live Market Trading.

Places real market buy orders on Binance. Enforces strict safety rules
such as anti-duplication checks and real fiat balance verification.

Usage: Called natively by main.py when mode="live".
"""

import logging
from datetime import datetime, timezone, timedelta
import sqlite3

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

from bot.database import log_trade

logger = logging.getLogger(__name__)


def has_run_recently(db_path: str = "data/trades.db", hours: int = 48) -> bool:
    """
    Check if a LIVE trade has successfully occurred within the last N hours.
    Prevents duplicate buys if the bot is manually restarted on a Monday.
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        
        cur.execute(
            "SELECT COUNT(1) FROM trades WHERE phase = 'live' AND status = 'executed' AND timestamp >= ?",
            (cutoff,)
        )
        count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        logger.error(f"Failed to query database for recent runs: {e}")
        # Fail safe: if we can't read the DB, assume it HAS run to prevent duplicate buys
        return True


def run_live_trade(cfg: dict) -> None:
    """
    Execute a REAL market buy against the Binance API.

    Safety measures verified beforehand:
    1. Duplicate protection (via DB).
    2. API connectivity.
    3. Spot wallet AUD balance check + buffer.
    """
    pair = cfg["trading_pair"]
    amount_aud = cfg["buy_amount_aud"]
    min_balance = cfg["safety"]["min_balance_aud"]
    
    now_utc = datetime.now(tz=timezone.utc)
    ts = now_utc.isoformat()

    logger.warning("LIVE TRADE STARTING | %s | Requesting $%.2f AUD", pair, amount_aud)

    # ------------------------------------------------------------------
    # 1. Duplicate Order Guard
    # ------------------------------------------------------------------
    if has_run_recently():
        msg = "Duplicate order protection: A live trade was already executed in the last 48 hours."
        logger.error(msg)
        return

    # ------------------------------------------------------------------
    # 2. API Setup & Balance Check
    # ------------------------------------------------------------------
    client = Client(cfg["api_key"], cfg["api_secret"])
    
    try:
        # We need the fiat currency (e.g. AUD) to check balance.
        # Assuming pair ends in AUD (like BTCAUD).
        fiat = "AUD"
        if not pair.endswith(fiat):
            # Fallback if the user changes pair to BTCUSDT or similar later
            fiat = pair[3:] if len(pair) > 6 else pair[3:]  # rudimentary split
            if pair == "BTCUSDT":
                fiat = "USDT"

        asset_balance = client.get_asset_balance(asset=fiat)
        if not asset_balance:
            raise ValueError(f"Could not retrieve balance for {fiat}. Verify API keys have 'Reading' permission.")
            
        real_balance = float(asset_balance["free"])
        
    except BinanceAPIException as e:
        msg = f"Binance rejected balance request: [{e.status_code}] {e.message}"
        logger.error(msg)
        log_trade(phase="live", timestamp=ts, pair=pair, price_aud=0, aud_spent=amount_aud, btc_bought=0, status="error", notes=msg)
        return
    except BinanceRequestException as e:
        msg = f"Network error fetching balance: {e}"
        logger.error(msg)
        log_trade(phase="live", timestamp=ts, pair=pair, price_aud=0, aud_spent=0, btc_bought=0, status="error", notes=msg)
        return
    except Exception as e:
        msg = f"Unexpected error validating balance: {e}"
        logger.error(msg)
        log_trade(phase="live", timestamp=ts, pair=pair, price_aud=0, aud_spent=0, btc_bought=0, status="error", notes=msg)
        return

    required_balance = amount_aud + min_balance
    if real_balance < required_balance:
        msg = (
            f"Insufficient real balance! "
            f"Available: ${real_balance:.2f} {fiat}. "
            f"Required: ${required_balance:.2f} (Buy + Safety buffer)."
        )
        logger.warning(msg)
        log_trade(phase="live", timestamp=ts, pair=pair, price_aud=0, aud_spent=amount_aud, btc_bought=0, status="skipped", notes=msg)
        return

    # ------------------------------------------------------------------
    # 3. Market Buy Order Execution with Retry Wrapper
    # ------------------------------------------------------------------
    logger.info("Balance check passed (%.2f %s). Placing real market order...", real_balance, fiat)
    
    max_retries = cfg["safety"].get("max_retries", 3)
    delay_sec = cfg["safety"].get("retry_delay_seconds", 30)
    
    import time
    
    for attempt in range(1, max_retries + 1):
        try:
            order = client.order_market_buy(
                symbol=pair,
                quoteOrderQty=amount_aud
            )
            break  # Success
            
        except BinanceAPIException as e:
            msg = f"Binance rejected market order: [{e.status_code}] {e.message}"
            logger.error(f"CRITICAL: {msg}")
            log_trade(phase="live", timestamp=ts, pair=pair, price_aud=0, aud_spent=amount_aud, btc_bought=0, status="error", notes=msg)
            return
            
        except BinanceRequestException as e:
            if attempt == max_retries:
                msg = f"Network exception max retries reached: {e}"
                logger.error(f"CRITICAL: {msg}")
                log_trade(phase="live", timestamp=ts, pair=pair, price_aud=0, aud_spent=amount_aud, btc_bought=0, status="error", notes=msg)
                return
            logger.warning("Network error placing order (attempt %d/%d), sleeping %ds: %s", attempt, max_retries, delay_sec, e)
            time.sleep(delay_sec)

    # ------------------------------------------------------------------
    # 4. Parse execution results and log
    # ------------------------------------------------------------------
    try:
        # Binance returns the total quote (AUD) spent and base (BTC) received
        cummulative_quote_qty = float(order.get("cummulativeQuoteQty", amount_aud))
        executed_qty = float(order.get("executedQty", 0.0))
        order_id = str(order.get("orderId", ""))
        
        # Determine average execution price
        if executed_qty > 0:
            avg_price = cummulative_quote_qty / executed_qty
        else:
            avg_price = 0.0

        logger.info(
            "LIVE ORDER EXECUTED! | ID: %s | Spent: $%.2f | Bought: %.8f BTC | Avg Price: $%.2f", 
            order_id, cummulative_quote_qty, executed_qty, avg_price
        )

        log_trade(
            phase="live",
            timestamp=ts,
            pair=pair,
            price_aud=avg_price,
            aud_spent=cummulative_quote_qty,
            btc_bought=executed_qty,
            status="executed",
            order_id=order_id,
            notes=f"Order fully executed via '{fiat}' spot balance"
        )
    except Exception as e:
        logger.error(f"Order succeeded but failed to parse/log response: {e}")
        # Log a degraded event so the user knows an order *was* placed
        log_trade(
            phase="live",
            timestamp=ts,
            pair=pair,
            price_aud=0,
            aud_spent=amount_aud,
            btc_bought=0,
            status="error",
            notes=f"Order placed but logging failed: {e}"
        )
