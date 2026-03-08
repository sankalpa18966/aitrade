"""
scheduler.py — Forex AI
24/7 auto-run: morning brief, evening summary, breaking news, economic surprises.
"""

import logging
import sys
import time
from datetime import datetime, timezone

import schedule

import config
import main as pipeline

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ── SCHEDULED JOBS ────────────────────────────────────────────────

def job_morning_brief():
    logger.info("⏰ Scheduled: Morning Brief")
    pipeline.run_daily_brief()


def job_evening_summary():
    logger.info("⏰ Scheduled: Evening Summary")
    pipeline.run_evening_summary()


def job_breaking_news_check():
    """Every 5 min — breaking news RSS check."""
    count = pipeline.check_breaking_news()
    if count:
        logger.info(f"Breaking news: {count} alert(s) sent")


def job_economic_surprise_check():
    """Every 5 min — economic calendar surprise check."""
    count = pipeline.check_economic_surprises()
    if count:
        logger.info(f"Economic surprise: {count} alert(s) sent")


def job_keepalive():
    """Hourly heartbeat — just log, no Telegram."""
    logger.info(
        f"💓 Keep-alive | "
        f"Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )


# ── SCHEDULE SETUP ────────────────────────────────────────────────

def setup_schedules():
    # ── Daily briefs (UTC times) ─────────────────────────────────
    schedule.every().day.at(config.MORNING_BRIEF_TIME).do(job_morning_brief)
    schedule.every().day.at(config.EVENING_SUMMARY_TIME).do(job_evening_summary)

    # ── Breaking news + economic surprise (every 5 min) ──────────
    schedule.every(config.NEWS_CHECK_INTERVAL_MIN).minutes.do(job_breaking_news_check)
    schedule.every(config.NEWS_CHECK_INTERVAL_MIN).minutes.do(job_economic_surprise_check)

    # ── Hourly keep-alive ────────────────────────────────────────
    schedule.every().hour.do(job_keepalive)

    logger.info("=" * 50)
    logger.info("FOREX AI SCHEDULER STARTED")
    logger.info(f"Morning Brief : {config.MORNING_BRIEF_TIME} UTC daily")
    logger.info(f"Evening Summary: {config.EVENING_SUMMARY_TIME} UTC daily")
    logger.info(f"News Check    : Every {config.NEWS_CHECK_INTERVAL_MIN} minutes")
    logger.info("=" * 50)


# ── MAIN LOOP ─────────────────────────────────────────────────────

if __name__ == "__main__":
    setup_schedules()

    # Startup: run morning brief immediately once
    logger.info("Running initial brief on startup...")
    pipeline.run_daily_brief()

    logger.info("Entering main loop... (Ctrl+C to stop)")
    while True:
        try:
            schedule.run_pending()
            time.sleep(30)   # Check every 30 seconds
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user.")
            break
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}", exc_info=True)
            time.sleep(60)   # Wait and retry
