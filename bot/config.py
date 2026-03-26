"""
bot/config.py — Config loader for the DCA bot.

Loads config.yaml for all runtime parameters and .env for API keys.
Validates all required fields at startup — crashes immediately with a
clear message if anything is missing, so errors surface before trading
rather than mid-execution.

Usage:
    from bot.config import load_config
    cfg = load_config()
"""

import os
import sys

import yaml
from dotenv import load_dotenv

# Load .env from the project root (parent of this file's directory)
load_dotenv()


def load_config(path: str = "config.yaml") -> dict:
    """
    Load and validate the bot configuration.

    Reads config.yaml for all runtime parameters, then injects
    BINANCE_API_KEY and BINANCE_API_SECRET from the .env file.

    Args:
        path: Path to config.yaml (default: "config.yaml" in cwd).

    Returns:
        dict: Fully validated configuration dictionary.

    Side effects:
        Calls sys.exit() with a clear [FATAL] message on any
        missing file, invalid YAML, or missing required field.
        This is intentional — config errors must crash at startup.
    """
    # ----------------------------------------------------------------
    # 1. Load YAML — any parse error is unrecoverable at startup
    # ----------------------------------------------------------------
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        sys.exit(
            f"[FATAL] Config file not found: '{path}'\n"
            f"        Create config.yaml in the project root "
            f"(see config.yaml template)."
        )
    except yaml.YAMLError as e:
        sys.exit(f"[FATAL] Invalid YAML in config file '{path}': {e}")

    if not isinstance(cfg, dict):
        sys.exit(f"[FATAL] config.yaml is empty or not a valid YAML mapping.")

    # ----------------------------------------------------------------
    # 2. Inject API keys from .env — never stored in config.yaml
    # ----------------------------------------------------------------
    cfg["api_key"] = os.getenv("BINANCE_API_KEY", "").strip()
    cfg["api_secret"] = os.getenv("BINANCE_API_SECRET", "").strip()

    # ----------------------------------------------------------------
    # 3. Validate required fields — fail at startup, not mid-trade
    # ----------------------------------------------------------------

    # Always require mode, pair, and amount.
    # API keys are only required for forward_test and live — the backtest
    # uses only public Binance endpoints and works without credentials.
    required_fields = ["mode", "trading_pair", "buy_amount_aud"]
    for field in required_fields:
        if not cfg.get(field):
            sys.exit(
                f"[FATAL] Missing required config field: '{field}'.\n"
                f"        Check config.yaml."
            )

    if cfg["mode"] in ("forward_test", "live"):
        for key_field in ("api_key", "api_secret"):
            if not cfg.get(key_field):
                sys.exit(
                    f"[FATAL] MODE={cfg['mode']} requires '{key_field}'.\n"
                    f"        Set BINANCE_API_KEY and BINANCE_API_SECRET in your .env file."
                )

    # Validate mode value
    valid_modes = {"backtest", "forward_test", "live"}
    if cfg["mode"] not in valid_modes:
        sys.exit(
            f"[FATAL] Invalid mode '{cfg['mode']}' in config.yaml.\n"
            f"        Must be one of: {', '.join(sorted(valid_modes))}"
        )

    # Validate buy_amount_aud is a positive number
    try:
        amount = float(cfg["buy_amount_aud"])
        if amount <= 0:
            raise ValueError("must be > 0")
        cfg["buy_amount_aud"] = amount
    except (TypeError, ValueError) as e:
        sys.exit(
            f"[FATAL] 'buy_amount_aud' in config.yaml must be a positive number, "
            f"got: {cfg.get('buy_amount_aud')!r}"
        )

    # Validate backtest section exists when mode=backtest
    if cfg["mode"] == "backtest":
        if not cfg.get("backtest"):
            sys.exit("[FATAL] config.yaml is missing the 'backtest' section.")
        for key in ("start_date", "end_date"):
            if not cfg["backtest"].get(key):
                sys.exit(
                    f"[FATAL] config.yaml backtest section is missing '{key}'."
                )

    # Validate safety section exists for forward_test and live
    if cfg["mode"] in ("forward_test", "live"):
        if not cfg.get("safety"):
            sys.exit("[FATAL] config.yaml is missing the 'safety' section.")

    # Validate forward_test mock balance
    if cfg["mode"] == "forward_test":
        if not cfg.get("forward_test"):
            sys.exit("[FATAL] config.yaml is missing the 'forward_test' section.")
        try:
            cfg["forward_test"]["simulated_balance_aud"] = float(
                cfg["forward_test"].get("simulated_balance_aud", 1000.0)
            )
        except (TypeError, ValueError):
            sys.exit("[FATAL] 'simulated_balance_aud' must be a number.")

    return cfg
