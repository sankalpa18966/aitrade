"""
main.py — Forex AI
Full pipeline one-shot run karanna. Test + manual use ekata.
"""

import logging
import sys
from datetime import datetime, timezone

import config
import data_collector
import analyzer
import signal_generator
import telegram_bot

# ── Logging setup ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ── DAILY BRIEF PIPELINE ──────────────────────────────────────────

def run_daily_brief() -> bool:
    """
    Complete pipeline: collect → analyze → signal → send.
    Returns True if brief sent OK.
    """
    logger.info("=" * 50)
    logger.info("DAILY BRIEF STARTING")
    logger.info("=" * 50)

    try:
        # 1. Collect data
        data = data_collector.collect_all_data()
        logger.info(f"Data collected: {len(data['headlines'])} headlines, "
                    f"{len(data['calendar_events'])} events")

        # 2. Analyze
        analysis = analyzer.analyze_daily_sentiment(data)
        if not analysis:
            logger.error("Analysis failed — empty result from Gemini")
            telegram_bot.send_message(
                "⚠️ Bandafx AI: Daily brief failed (Gemini error). Check logs."
            )
            return False

        currency_scores = analysis.get("currency_scores", {})
        logger.info(f"Analysis OK — Mood: {analysis.get('market_mood')} "
                    f"| Confidence: {analysis.get('confidence')}%")

        # 3. Generate signal message
        brief_message = signal_generator.format_daily_brief(analysis, currency_scores)

        # 4. Send Telegram
        ok = telegram_bot.send_message(brief_message)
        if ok:
            logger.info("Daily brief sent to Telegram ✅")
        else:
            logger.error("Telegram send failed")

        return ok

    except Exception as e:
        logger.error(f"run_daily_brief exception: {e}", exc_info=True)
        try:
            telegram_bot.send_message(
                f"⚠️ Bandafx AI Error: {str(e)[:200]}"
            )
        except Exception:
            pass
        return False


# ── EVENING SUMMARY PIPELINE ──────────────────────────────────────

def run_evening_summary() -> bool:
    """Light evening recap — uses same pipeline but lighter message."""
    logger.info("EVENING SUMMARY STARTING")
    try:
        data     = data_collector.collect_all_data()
        analysis = analyzer.analyze_daily_sentiment(data)
        if not analysis:
            return False

        currency_scores = analysis.get("currency_scores", {})
        msg = signal_generator.format_evening_summary(analysis, currency_scores)
        ok  = telegram_bot.send_message(msg)
        if ok:
            logger.info("Evening summary sent ✅")
        return ok

    except Exception as e:
        logger.error(f"run_evening_summary exception: {e}", exc_info=True)
        return False


# ── BREAKING NEWS CHECK ───────────────────────────────────────────

def check_breaking_news() -> int:
    """
    New high-impact headlines check karanna.
    Already sent ones skip (seen cache). 
    Returns number of alerts sent.
    """
    headlines = data_collector.fetch_recent_high_impact_news()
    new_ones  = data_collector.get_new_headlines_only(headlines)

    if not new_ones:
        logger.debug("No new high-impact headlines.")
        return 0

    sent = 0
    for headline in new_ones[:3]:   # Max 3 per check
        title   = headline["title"]
        summary = headline.get("summary", "")

        logger.info(f"Breaking news detected: {title}")
        analysis = analyzer.analyze_breaking_news(title, summary)

        if not analysis:
            continue

        if not analysis.get("is_forex_relevant", False):
            logger.info("Not forex relevant — skip.")
            continue

        if analysis.get("impact_level", "LOW") == "LOW":
            logger.info("Low impact — skip.")
            continue

        ok = telegram_bot.send_breaking_news_alert(title, analysis)
        if ok:
            sent += 1
            logger.info(f"Breaking news alert sent: {title[:60]}")
            
            # Hedge Fund trick: Immediately trigger an intraday scan if big news hits
            logger.info("Big news hit! Triggering immediate SMC intraday scan...")
            run_intraday_scan()

    return sent


# ── ECONOMIC SURPRISE CHECK ───────────────────────────────────────

def check_economic_surprises() -> int:
    """
    Calendar events fetch → Actual vs Forecast compare → Surprise alert send.
    Returns number of alerts sent.
    """
    events    = data_collector.fetch_forexfactory_calendar()
    surprises = data_collector.detect_economic_surprise(events)

    if not surprises:
        logger.debug("No economic surprises.")
        return 0

    sent = 0
    for ev in surprises:
        logger.info(
            f"Economic surprise: {ev['event']} | "
            f"{ev['forecast']} → {ev['actual']} ({ev['deviation']} {ev['beat_miss']})"
        )
        analysis = analyzer.analyze_economic_surprise(ev)
        if not analysis:
            continue

        ok = telegram_bot.send_economic_surprise_alert(ev, analysis)
        if ok:
            sent += 1
            logger.info(f"Surprise alert sent: {ev['event']}")

    return sent


# ── INTRADAY SMC SCANNER (PREMIUM) ────────────────────────────────

def run_intraday_scan():
    """
    Day time eke continuous market eka scan karala, morning eke miss wunu 
    hoda FVG/OB entries allanna. (Uses allowed AI calls).
    """
    logger.info("=" * 50)
    logger.info("INTRADAY SMC SCAN STARTING")
    logger.info("=" * 50)

    # 1. Very light news scan to check if bias changed
    data = data_collector.collect_daily_data()
    analysis = analyzer.analyze_daily_sentiment(data)
    if not analysis:
        logger.error("Analysis failed during intraday scan.")
        return

    currency_scores = analysis.get("currency_scores", {})
    pairs = config.CURRENCY_PAIRS

    new_signals_found = 0

    for idx, pair in enumerate(pairs):
        base, quote = pair.split("/")
        base_score = currency_scores.get(base, 0)
        quote_score = currency_scores.get(quote, 0)
        diff = base_score - quote_score

        # Determine AI directional bias
        ai_direction = "NEUTRAL"
        if diff >= 1.5:   ai_direction = "BUY"
        elif diff <= -1.5: ai_direction = "SELL"
        
        if ai_direction == "NEUTRAL":
            continue
            
        logger.info(f"[{pair}] Intraday AI Bias: {ai_direction} (Diff: {diff:.1f})")

        # Get exact entry from SMC Engine
        signal = signal_generator.generate_smc_signal(pair, ai_direction)
        
        if signal:
            import tracker
            if tracker.has_open_trade(pair):
                logger.info(f"[{pair}] Skipping Intraday setup — trade already active.")
                continue
            
            # Send immediately!
            telegram_bot.send_smc_signal(signal)
            new_signals_found += 1
        
        # small delay
        time.sleep(2)

    logger.info(f"Intraday scan complete. {new_signals_found} new setups found.")


# ── MAIN ENTRY ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  FOREX AI — MANUAL RUN")
    print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 50)
    print("\nRunning full daily brief pipeline...\n")
    success = run_daily_brief()
    print(f"\nResult: {'✅ Brief sent!' if success else '❌ Failed — check errors.log'}")
