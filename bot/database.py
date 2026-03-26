"""
bot/database.py — SQLite trade log for the DCA bot.

All three phases (backtest, forward_test, live) write to the same
'trades' table so results are directly comparable across phases.

The DB path is read from the module-level DB_PATH constant. Call
init_db() once at startup (from main.py) to create the table.

Usage:
    from bot.database import init_db, log_trade, trade_exists_today
    init_db()
    log_trade(phase="backtest", timestamp=..., ...)
"""

import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

# SQLite file created automatically on first run.
# 'data/' directory is created by main.py before init_db() is called.
DB_PATH = "data/trades.db"


def init_db() -> None:
    """
    Create the trades table if it does not already exist.

    Safe to call on every startup — uses CREATE TABLE IF NOT EXISTS.
    Must be called before any log_trade() or trade_exists_today() call.
    """
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
    logger.debug("Database initialised: %s", DB_PATH)


def log_trade(
    phase: str,
    timestamp: str,
    pair: str,
    price_aud: float,
    aud_spent: float,
    btc_bought: float,
    order_id: str = None,
    status: str = "simulated",
    notes: str = None,
) -> None:
    """
    Insert one trade record into the trades table.

    Args:
        phase:      'backtest', 'forward_test', or 'live'
        timestamp:  ISO 8601 UTC datetime string
        pair:       Trading pair, e.g. 'AUDBTC'
        price_aud:  BTC price in AUD at time of trade
        aud_spent:  AUD amount spent (or attempted)
        btc_bought: BTC received (0 for skipped/error rows)
        order_id:   Binance order ID (None for simulated phases)
        status:     'simulated' | 'filled' | 'skipped' | 'error'
        notes:      Free-text detail — error messages or skip reasons
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO trades
            (phase, timestamp, pair, price_aud, aud_spent, btc_bought,
             order_id, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (phase, timestamp, pair, price_aud, aud_spent, btc_bought,
         order_id, status, notes),
    )
    conn.commit()
    conn.close()


def trade_exists_today(phase: str, date_str: str) -> bool:
    """
    Return True if a trade for this phase was already logged today.

    Used by the live phase as a duplicate-order guard — ensures at most
    one order is placed per Monday regardless of restarts.

    Args:
        phase:    'backtest', 'forward_test', or 'live'
        date_str: Date as 'YYYY-MM-DD' (UTC)

    Returns:
        bool: True if any row matches phase + date prefix in timestamp.
    """
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        """
        SELECT id FROM trades
        WHERE phase = ? AND timestamp LIKE ?
        LIMIT 1
        """,
        (phase, f"{date_str}%"),
    ).fetchone()
    conn.close()
    return row is not None
