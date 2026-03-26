"""
main.py — Entry point for the DCA bot.

Sets up logging and directories, loads config, initialises the
database, then routes to the correct engine based on MODE:

  backtest     → Runs synchronously and exits.
  forward_test → Starts the APScheduler (blocking) and waits for Mondays.
  live         → Starts the APScheduler (blocking) and waits for Mondays.

Scheduler jobs are wrapped in a top-level except block (per skill rules)
so an unhandled exception in a job does NOT silently kill the scheduler.
"""

import logging
import os
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ----------------------------------------------------------------
# Ensure output directories exist before logging is configured
# ----------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)

# ----------------------------------------------------------------
# Logging — file + stdout, matching format from skill
# ----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------
# Config and DB — imported after directories exist
# ----------------------------------------------------------------
from bot.config import load_config
from bot.database import init_db


# ----------------------------------------------------------------
# Scheduler job factory
# ----------------------------------------------------------------

def make_job(cfg: dict):
    """
    Build and return the scheduled job function for the active mode.

    The returned function is wrapped in a top-level except block.
    This is critical per the skill: if the job raises and the exception
    propagates, APScheduler removes the job silently — the bot looks
    alive but never trades again.

    Args:
        cfg: Validated config dict.

    Returns:
        Callable: The safe_job() closure, ready to pass to scheduler.add_job().

    Raises:
        ValueError: If called with mode='backtest' (not schedulable).
    """
    mode = cfg["mode"]

    if mode == "forward_test":
        from bot.forward_test import run_forward_test
        fn = lambda: run_forward_test(cfg)

    elif mode == "live":
        from bot.live import run_live_trade
        fn = lambda: run_live_trade(cfg)

    else:
        raise ValueError(
            f"make_job() called with non-schedulable mode: '{mode}'. "
            "Only 'forward_test' and 'live' use the scheduler."
        )

    def safe_job():
        """
        Top-level job wrapper. Catches ALL exceptions to keep the
        scheduler alive. The only acceptable broad except in the codebase.
        """
        try:
            fn()
        except Exception as e:
            logger.error(
                "Scheduled job failed — scheduler preserved for next Monday: %s",
                e,
                exc_info=True,
            )
            logger.info("Next Monday fire is still scheduled.")

    return safe_job


# ----------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------

if __name__ == "__main__":
    cfg = load_config()
    init_db()

    mode = cfg["mode"]
    logger.info("DCA Bot starting | mode=%s | pair=%s | amount=A$%.2f",
                mode.upper(), cfg["trading_pair"], cfg["buy_amount_aud"])

    # ---- Phase 1: Backtest ----
    if mode == "backtest":
        from bot.backtest import run_backtest
        try:
            run_backtest(cfg)
        except Exception as e:
            # Let the traceback appear in full — do not swallow it.
            # Backtest is not a live process, so crashing here is correct.
            logger.error("Backtest failed: %s", e, exc_info=True)
            sys.exit(1)

    # ---- Phase 2 & 3: Scheduler modes ----
    elif mode in ("forward_test", "live"):
        # Parse schedule from config — convert AEST to UTC offset.
        # AEST = UTC+10, AEDT = UTC+11. The skill hardcodes 23:00 UTC
        # for 09:00 AEST. We read the time from config and apply the
        # standard AEST offset (UTC+10, non-daylight-saving).
        # ⚠️  ASSUMPTION: Fixed UTC+10 offset (AEST). If you need AEDT
        #     support (UTC+11 in summer), update this calculation.
        schedule_time = cfg.get("schedule", {}).get("time", "09:00")
        hour_aest, minute = map(int, schedule_time.split(":"))
        hour_utc = (hour_aest - 10) % 24  # AEST → UTC

        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            make_job(cfg),
            CronTrigger(day_of_week="mon", hour=hour_utc, minute=minute),
            misfire_grace_time=120,
            coalesce=True,
            max_instances=1,
        )

        scheduler.start()
        print(
            f"\n  [OK]    DCA Bot running  | mode={mode.upper()}\n"
            f"  [TIME]  Weekly buy       | Monday {schedule_time} AEST\n"
            f"  [INFO]  Press Ctrl+C to stop.\n"
        )

        try:
            # Keep the main thread alive so it can catch Ctrl+C
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot shut down by user (KeyboardInterrupt).")
            scheduler.shutdown(wait=False)
            print("\n  Bot stopped.\n")

    else:
        # Should never reach here — load_config() validates mode
        logger.error("Unknown mode in config: '%s'", mode)
        sys.exit(1)
