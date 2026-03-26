import unittest
from unittest.mock import patch, MagicMock
from binance.exceptions import BinanceAPIException, BinanceRequestException


# ─── Config Tests ─────────────────────────────────────────────────────────────

class TestConfig(unittest.TestCase):
    """Tests for bot/config.py — startup validation and .env loading."""

    def test_missing_api_key_exits(self):
        """Bot must crash at startup if BINANCE_API_KEY is not set."""
        with patch("os.getenv", return_value=None):
            with self.assertRaises(SystemExit):
                from bot.config import load_config
                load_config()

    def test_invalid_mode_exits(self):
        """Bot must crash at startup if MODE is not a valid option."""
        mock_cfg = {
            "mode": "invalid_mode",
            "trading_pair": "BTCAUD",
            "buy_amount_aud": 100,
            "backtest": {"start_date": "2021-01-01", "end_date": "2024-01-01"},
            "forward_test": {"simulated_balance_aud": 1000},
            "safety": {"min_balance_aud": 10, "max_retries": 3, "retry_delay_seconds": 30}
        }
        with patch("builtins.open"), \
             patch("yaml.safe_load", return_value=mock_cfg), \
             patch("os.getenv", return_value="fake_key"):
            with self.assertRaises(SystemExit):
                from bot.config import load_config
                load_config()

    def test_valid_config_loads(self):
        """Valid config with all required fields should load without error."""
        mock_cfg = {
            "mode": "backtest",
            "trading_pair": "BTCAUD",
            "buy_amount_aud": 100,
            "backtest": {"start_date": "2021-01-01", "end_date": "2024-01-01"},
            "forward_test": {"simulated_balance_aud": 1000},
            "safety": {"min_balance_aud": 10, "max_retries": 3, "retry_delay_seconds": 30}
        }
        with patch("builtins.open"), \
             patch("yaml.safe_load", return_value=mock_cfg), \
             patch("os.getenv", return_value="fake_key"):
            from bot.config import load_config
            cfg = load_config()
            self.assertEqual(cfg["mode"], "backtest")
            self.assertEqual(cfg["trading_pair"], "BTCAUD")


# ─── Database Tests ────────────────────────────────────────────────────────────

class TestDatabase(unittest.TestCase):
    """Tests for bot/database.py — trade logging and duplicate detection."""

    def setUp(self):
        """Use a temp file for every test to ensure persistence between connections."""
        import os
        import tempfile
        from bot import database
        self.db_fd, self.db_path = tempfile.mkstemp()
        os.close(self.db_fd)  # Close the fd so SQLite can use the file on Windows
        database.DB_PATH = self.db_path
        database.init_db()

    def tearDown(self):
        import os
        os.unlink(self.db_path)

    def test_log_trade_writes_row(self):
        """log_trade() should insert one row into the trades table."""
        from bot.database import log_trade, DB_PATH
        import sqlite3
        log_trade("backtest", "2024-01-01T00:00:00+00:00", "BTCAUD",
                  50000.0, 100.0, 0.002, status="simulated")
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT * FROM trades").fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], "backtest")   # phase
        self.assertEqual(rows[0][8], "simulated")  # status

    def test_has_run_recently_returns_true(self):
        """has_run_recently() must return True when a same-day trade is logged."""
        from bot.database import log_trade
        from bot.live import has_run_recently
        from datetime import datetime, timezone
        from bot import database
        
        now = datetime.now(timezone.utc).isoformat()
        log_trade("live", now, "BTCAUD", 50000.0, 100.0, 0.002, order_id="12345", status="executed")
        
        # Test function from live module
        self.assertTrue(has_run_recently(database.DB_PATH, 48))

    def test_has_run_recently_returns_false_for_old_trade(self):
        """has_run_recently() must return False when no trade exists in window."""
        from bot.database import log_trade
        from bot.live import has_run_recently
        from bot import database
        
        # 3 days ago
        old = "2024-06-03T23:00:00+00:00"
        log_trade("live", old, "BTCAUD", 50000.0, 100.0, 0.002, order_id="12345", status="executed")
        
        self.assertFalse(has_run_recently(database.DB_PATH, 48))


# ─── Live Phase Tests ──────────────────────────────────────────────────────────

class TestLive(unittest.TestCase):
    """Tests for bot/live.py — kill switch, duplicate guard, retry logic."""

    def _make_cfg(self):
        return {
            "api_key": "fake", "api_secret": "fake",
            "trading_pair": "BTCAUD", "buy_amount_aud": 100,
            "safety": {"min_balance_aud": 10, "max_retries": 3, "retry_delay_seconds": 0}
        }
        
    def setUp(self):
        import os
        import tempfile
        from bot import database
        self.db_fd, self.db_path = tempfile.mkstemp()
        os.close(self.db_fd)  # Close the fd so SQLite can use the file on Windows
        database.DB_PATH = self.db_path
        database.init_db()

    def tearDown(self):
        import os
        os.unlink(self.db_path)

    @patch("bot.live.has_run_recently", return_value=False)
    @patch("bot.live.Client")
    def test_kill_switch_skips_when_balance_too_low(self, mock_client, _):
        """Kill switch must skip the order and log 'skipped' when balance is insufficient."""
        from bot.live import run_live_trade
        from bot.database import DB_PATH
        import sqlite3

        mock_instance = mock_client.return_value
        mock_instance.get_asset_balance.return_value = {"free": "50.0"}  # below 100 + 10

        run_live_trade(self._make_cfg())

        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT status FROM trades LIMIT 1").fetchone()
        conn.close()
        self.assertEqual(row[0], "skipped")

    @patch("bot.live.has_run_recently", return_value=True)
    @patch("bot.live.Client")
    def test_duplicate_guard_blocks_second_order(self, mock_client, _):
        """Duplicate guard must return early without placing an order on the same Monday."""
        from bot.live import run_live_trade

        run_live_trade(self._make_cfg())

        # Client should be initialised but order_market_buy must never be called
        mock_client.return_value.order_market_buy.assert_not_called()

    @patch("bot.live.has_run_recently", return_value=False)
    @patch("bot.live.Client")
    def test_api_exception_is_not_retried(self, mock_client, _):
        """BinanceAPIException must not trigger retry — it should fail immediately."""
        from bot.live import run_live_trade

        mock_instance = mock_client.return_value
        mock_instance.get_asset_balance.return_value = {"free": "500.0"}
        mock_instance.get_symbol_ticker.return_value = {"price": "50000.0"}

        api_error = BinanceAPIException(MagicMock(status_code=400), 400, '{"code": -1013}')
        mock_instance.order_market_buy.side_effect = api_error

        run_live_trade(self._make_cfg())

        # Should only be called once — no retries on API rejection
        self.assertEqual(mock_instance.order_market_buy.call_count, 1)

    @patch("time.sleep")
    @patch("bot.live.has_run_recently", return_value=False)
    @patch("bot.live.Client")
    def test_network_error_retries_up_to_max(self, mock_client, _, mock_sleep):
        """BinanceRequestException must retry up to max_retries times."""
        from bot.live import run_live_trade

        mock_instance = mock_client.return_value
        mock_instance.get_asset_balance.return_value = {"free": "500.0"}
        mock_instance.get_symbol_ticker.return_value = {"price": "50000.0"}
        mock_instance.order_market_buy.side_effect = BinanceRequestException("timeout")

        run_live_trade(self._make_cfg())

        # Should be called 3 times total
        self.assertEqual(mock_instance.order_market_buy.call_count, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
