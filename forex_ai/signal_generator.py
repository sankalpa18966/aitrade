"""
signal_generator.py — Forex AI
Currency scores gena pairs rank karanna + Telegram message format.
"""

import logging
from datetime import datetime, timezone

import config

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


def _get_bias(score: float) -> str:
    if score >= 2:   return "STRONG BULL"
    if score >= 0.5: return "BULL"
    if score <= -2:  return "STRONG BEAR"
    if score <= -0.5:return "BEAR"
    return "NEUTRAL"


def rank_currencies(currency_scores: dict) -> list[tuple]:
    """
    Scores sort karanna — strongest to weakest.
    Returns: [(currency, score), ...]
    """
    return sorted(currency_scores.items(), key=lambda x: x[1], reverse=True)


def find_top_signals(ranked: list[tuple], max_signals: int = None) -> list[dict]:
    """
    Strongest vs Weakest pair karana top signals find karanna.
    Only config.FOREX_PAIRS eke inna pairs use.
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

            # Check both directions against allowed pairs
            pair_a = f"{strong_cur}/{weak_cur}"
            pair_b = f"{weak_cur}/{strong_cur}"

            if pair_a in config.FOREX_PAIRS and pair_a not in checked:
                checked.add(pair_a)
                score_diff = abs(strong_score - weak_score)
                conf = min(95, int(50 + score_diff * 7))
                signals.append({
                    "pair"       : pair_a,
                    "direction"  : "BUY",
                    "strong"     : strong_cur,
                    "weak"       : weak_cur,
                    "fund_score" : round(score_diff / 2, 1),
                    "confidence" : conf,
                    "bias"       : f"BUY {strong_cur} strength vs {weak_cur} weakness",
                })
            elif pair_b in config.FOREX_PAIRS and pair_b not in checked:
                checked.add(pair_b)
                score_diff = abs(strong_score - weak_score)
                conf = min(95, int(50 + score_diff * 7))
                signals.append({
                    "pair"       : pair_b,
                    "direction"  : "SELL",
                    "strong"     : strong_cur,
                    "weak"       : weak_cur,
                    "fund_score" : round(score_diff / 2, 1),
                    "confidence" : conf,
                    "bias"       : f"SELL {weak_cur} weakness vs {strong_cur} strength",
                })

    return signals


def format_daily_brief(
    analysis: dict,
    currency_scores: dict,
) -> str:
    """
    Telegram ekata yavanna formatted daily brief message heda.
    """
    now     = datetime.now(timezone.utc)
    date_str = now.strftime("%d %b %Y — %H:%M UTC")
    mood    = analysis.get("market_mood", "neutral").upper()
    conf    = analysis.get("confidence", "?")
    drivers = analysis.get("drivers", [])
    upcoming = analysis.get("upcoming_high_impact", [])
    summary  = analysis.get("analysis_summary", "")

    ranked  = rank_currencies(currency_scores)
    signals = find_top_signals(ranked)

    # ── Currency Strength Table ──
    strength_lines = ""
    for i, (cur, score) in enumerate(ranked, 1):
        label = _bias_label(score)
        bar = "█" * int(abs(score)) if abs(score) >= 1 else "·"
        strength_lines += f"  {i}. {cur}  {score:+.1f}  {label}\n"

    # ── Top Signals ──
    signal_lines = ""
    for i, sig in enumerate(signals, 1):
        signal_lines += (
            f"\n  {i}. <b>{sig['pair']}</b> — {sig['direction']} BIAS\n"
            f"     Score: {sig['fund_score']}/5  |  Confidence: {sig['confidence']}%\n"
            f"     Reason: {sig['bias']}\n"
            f"     ⚠️  Wait for PA confirmation\n"
        )

    # ── Drivers ──
    driver_lines = "\n".join([f"  • {d}" for d in drivers[:4]])

    # ── Upcoming Events ──
    event_lines = "\n".join([f"  ⏰ {e}" for e in upcoming[:5]])
    if not event_lines:
        event_lines = "  No major events in next 24h"

    msg = (
        f"📊 <b>FOREX AI — DAILY BRIEF</b>\n"
        f"🗓️ {date_str}\n"
        f"{'─'*32}\n\n"
        f"🌍 <b>Market Mood:</b> {mood}  |  AI Confidence: {conf}%\n\n"
        f"📌 <b>Key Drivers:</b>\n{driver_lines}\n\n"
        f"💪 <b>Currency Strength Ranking:</b>\n{strength_lines}\n"
        f"🎯 <b>Top Setups:</b>{signal_lines}\n"
        f"⚡ <b>High-Impact Events:</b>\n{event_lines}\n\n"
        f"🤖 <i>{summary}</i>\n\n"
        f"⚠️  <i>AI = Bias only. Always confirm on chart!</i>"
    )
    return msg


def format_evening_summary(analysis: dict, currency_scores: dict) -> str:
    """Light evening summary message."""
    ranked = rank_currencies(currency_scores)
    top3   = ranked[:3]
    bot3   = ranked[-3:]

    lines = "  💪 Strong: " + " | ".join([f"{c} {s:+.1f}" for c, s in top3]) + "\n"
    lines += "  😔 Weak:   " + " | ".join([f"{c} {s:+.1f}" for c, s in bot3])

    msg = (
        f"🌙 <b>FOREX AI — EVENING RECAP</b>\n"
        f"{'─'*32}\n\n"
        f"{lines}\n\n"
        f"🌍 Mood: {analysis.get('market_mood','?').upper()}\n\n"
        f"<i>{analysis.get('analysis_summary','')}</i>\n\n"
        f"⚠️  <i>AI = Bias only. Always confirm on chart!</i>"
    )
    return msg


# ── Quick Test ────────────────────────────────────────────────────
if __name__ == "__main__":
    dummy_scores = {
        "USD":  3.2, "EUR": -2.8, "GBP":  1.5,
        "JPY": -1.0, "AUD":  0.8, "CAD":  0.3,
        "NZD": -0.5, "CHF": -1.8
    }
    dummy_analysis = {
        "market_mood"       : "risk-off",
        "confidence"        : 72,
        "drivers"           : [
            "Fed hawkish tone supports USD",
            "EU growth concerns weigh on EUR",
            "UK CPI beat boosts GBP"
        ],
        "upcoming_high_impact": [
            "16:30 USD - CPI y/y | F:3.1%",
            "18:00 EUR - ECB Rate Decision"
        ],
        "analysis_summary"  : "USD dominates on hawkish Fed, EUR under pressure from weak growth data.",
    }
    msg = format_daily_brief(dummy_analysis, dummy_scores)
    print(msg)
