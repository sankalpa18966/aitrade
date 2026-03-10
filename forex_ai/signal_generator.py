"""
signal_generator.py — Forex AI
Currency scores gena pairs rank karanna + SMC Engine eken Pinpoint Entry aran Telegram message format.
"""

import logging
import time
from datetime import datetime, timezone

import config
import smc_engine
import tracker

logger = logging.getLogger(__name__)

BIAS_LABELS = {
    range(4,  6):  "🔥 STRONG BULL",
    range(2,  4):  "🟢 Bullish",
    range(1,  2):  "🔼 Mild Bull",
    range(-1, 1):  "➡️  Neutral",
    range(-2, 0):  "🔽 Mild Bear",
    range(-4, -2): "🔴 Bearish",
    range(-6, -4): "❄️  STRONG BEAR",
}


def _bias_label(score: float) -> str:
    for rng, label in BIAS_LABELS.items():
        if int(score) in rng or (score >= 4):
            return label
    return "➡️  Neutral"


def rank_currencies(currency_scores: dict) -> list[tuple]:
    """Scores sort karanna — strongest to weakest."""
    return sorted(currency_scores.items(), key=lambda x: x[1], reverse=True)


def find_top_signals(ranked: list[tuple], max_signals: int = None) -> list[dict]:
    """
    Strongest vs Weakest pair aran smc_engine eken pinpoint order ganna.
    """
    if max_signals is None:
        max_signals = config.MAX_SIGNALS_PER_DAY

    signals = []
    checked = set()

    n = len(ranked)
    for i in range(n):
        for j in range(n - 1, i, -1):
            if len(signals) >= max_signals:
                break

            strong_cur, strong_score = ranked[i]
            weak_cur,   weak_score   = ranked[j]

            if strong_cur == weak_cur:
                continue

            pair_a = f"{strong_cur}/{weak_cur}"
            pair_b = f"{weak_cur}/{strong_cur}"

            # Check Pair A (BUY Bias)
            if pair_a in config.FOREX_PAIRS and pair_a not in checked:
                checked.add(pair_a)
                # Ensure the AI bias score difference is strong enough
                if strong_score - weak_score >= 1.5:
                    logger.info(f"Checking SMC for {pair_a} (BUY)")
                    current_price = tracker._get_current_price(pair_a)
                    if current_price:
                        sig = smc_engine.generate_pinpoint_signal(pair_a, "BUY", current_price)
                        if sig:
                            sig["fund_score"] = round(abs(strong_score - weak_score) / 2, 1)
                            signals.append(sig)

            # Check Pair B (SELL Bias)
            elif pair_b in config.FOREX_PAIRS and pair_b not in checked:
                checked.add(pair_b)
                if strong_score - weak_score >= 1.5:
                    logger.info(f"Checking SMC for {pair_b} (SELL)")
                    current_price = tracker._get_current_price(pair_b)
                    if current_price:
                        sig = smc_engine.generate_pinpoint_signal(pair_b, "SELL", current_price)
                        if sig:
                            sig["fund_score"] = round(abs(strong_score - weak_score) / 2, 1)
                            signals.append(sig)
                            
            # Add small delay to avoid yfinance rate limits
            time.sleep(1)

    return signals


def format_daily_brief(
    analysis: dict,
    currency_scores: dict,
) -> str:
    """Telegram ekata yawanna formatted Hedge Fund style message."""
    now     = datetime.now(timezone.utc)
    date_str = now.strftime("%d %b %Y — %H:%M UTC")
    mood    = analysis.get("market_mood", "neutral").upper()
    drivers = analysis.get("drivers", [])
    upcoming = analysis.get("upcoming_high_impact", [])

    ranked  = rank_currencies(currency_scores)
    signals = find_top_signals(ranked)
    
    # Track new signals (Only if AI gave it a pass)
    for sig in signals:
        tracker.save_signal(sig['pair'], sig['direction'], sig['entry'], sig['sl'], sig['tp'])

    # Get Bot Accuracy Stats
    stats = tracker.get_win_rate_stats()
    win_rate_str = f"{stats['win_rate']}%  |  W:{stats['wins']} L:{stats['losses']}"

    # ── Currency Strength Table ──
    strength_lines = ""
    for i, (cur, score) in enumerate(ranked[:5], 1): # Top 5 only to save space
        label = _bias_label(score)
        strength_lines += f"  {i}. {cur}  {score:+.1f}  {label}\n"

    # ── Top Signals (SMC Exact Entries) ──
    signal_lines = ""
    for i, sig in enumerate(signals, 1):
        direction_icon = "🟢" if sig['direction'] == "BUY" else "🔴"
        ai_score = sig.get('ai_quality_score', 'N/A')
        ai_reason = sig.get('ai_reasoning', '')
        score_text = f"     🧠 AI Rating: <b>{ai_score}/10</b>\n     📝 Reason: {ai_reason[:150]}...\n" if ai_score != 'N/A' else ""

        # Change Entry Type string to remove SMC jargon
        entry_str = str(sig['entry_type']).replace(" (OB)", "").replace(" (FVG)", "")
        
        signal_lines += (
            f"\n  {i}. {direction_icon} <b>{sig['pair']} — {entry_str}</b>\n"
            f"     🎯 Entry: <code>{sig['entry']}</code>\n"
            f"     🛡️ SL: <code>{sig['sl']}</code>\n"
            f"     💰 TP: <code>{sig['tp']}</code>  (1:{sig.get('risk_reward', 2.0)})\n"
            f"{score_text}"
        )
        
    if not signals:
        signal_lines = "\n  No high conviction setups right now.\n"

    # ── Upcoming Events ──
    event_lines = "\n".join([f"  ⏰ {e}" for e in upcoming[:3]])
    if not event_lines:
        event_lines = "  No major events in next 24h"

    msg = (
        f"📊 <b>BANDAFX AI — DAILY BRIEF</b>\n"
        f"🗓️ {date_str}\n"
        f"{'─'*32}\n\n"
        f"🌍 <b>Market Mood:</b> {mood}\n"
        f"📈 <b>Algorithm Win Rate:</b> <b>{win_rate_str}</b>\n\n"
        f"💪 <b>Top Currency Strength:</b>\n{strength_lines}\n"
        f"🎯 <b>Quantitative Setups:</b>{signal_lines}\n"
        f"⚡ <b>High-Impact Events:</b>\n{event_lines}\n\n"
        f"⚠️  <i>Use proper risk management (1-2% per trade).</i>"
    )
    return msg


def format_evening_summary(analysis: dict, currency_scores: dict) -> str:
    """Light evening summary with win-loss updates."""
    # Update trades before reporting stats
    tracker.update_pending_and_active_trades()
    stats = tracker.get_win_rate_stats()
    
    ranked = rank_currencies(currency_scores)
    top3   = ranked[:3]
    bot3   = ranked[-3:]

    lines = "  💪 Strong: " + " | ".join([f"{c} {s:+.1f}" for c, s in top3]) + "\n"
    lines += "  😔 Weak:   " + " | ".join([f"{c} {s:+.1f}" for c, s in bot3])

    msg = (
        f"🌙 <b>FOREX AI — EVENING RECAP</b>\n"
        f"{'─'*32}\n\n"
        f"📊 <b>Current Algorithm Stats:</b>\n"
        f"  • Win Rate: <b>{stats['win_rate']}%</b>\n"
        f"  • Closed Trades: {stats['total_closed']} (W: {stats['wins']}, L: {stats['losses']})\n"
        f"  • Active/Pending: {stats['open_trades']}\n\n"
        f"{lines}\n\n"
        f"🌍 Mood: {analysis.get('market_mood','?').upper()}\n\n"
        f"<i>{analysis.get('analysis_summary','')}</i>"
    )
    return msg

if __name__ == "__main__":
    dummy_scores = {
        "USD":  3.5, "EUR": -3.8, "GBP":  1.5,
        "JPY": -1.0, "AUD":  0.8, "CAD":  0.3,
        "NZD": -0.5, "CHF": -1.8
    }
    dummy_analysis = {
        "market_mood"       : "risk-off",
        "drivers"           : [
            "Fed hawkish tone supports USD"
        ],
        "upcoming_high_impact": [
            "16:30 USD - CPI y/y | F:3.1%"
        ],
        "analysis_summary"  : "USD dominates on hawkish Fed.",
    }
    
    # Make sure we init db for local test
    tracker.init_db()
    msg = format_daily_brief(dummy_analysis, dummy_scores)
    print(msg)

