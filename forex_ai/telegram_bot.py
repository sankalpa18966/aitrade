"""
telegram_bot.py — Forex AI
Telegram ekata messages yavana single file.
"""

import logging
import requests
import config

logger = logging.getLogger(__name__)

# ── Base URL ──────────────────────────────────────────────────────
BASE_URL = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"


def send_message(text: str) -> bool:
    """
    Plain text message send karanna.
    Returns True if successful, False otherwise.
    """
    try:
        url = f"{BASE_URL}/sendMessage"
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("Telegram message sent OK")
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def send_alert(title: str, message: str) -> bool:
    """
    Formatted alert — title bold, message below.
    """
    full_text = f"<b>{title}</b>\n\n{message}"
    return send_message(full_text)


def send_daily_brief(signal_message: str) -> bool:
    """
    Daily morning/evening brief yavanna.
    """
    header = "📊 <b>BANDAFX AI — DAILY BRIEF</b>\n" + "─" * 30 + "\n"
    return send_message(header + signal_message)


def send_breaking_news_alert(headline: str, analysis: dict) -> bool:
    """
    Breaking news detect wunama real-time alert yavanna.

    analysis dict expected keys:
      currencies  : list  — ["USD", "EUR"]
      impact      : str   — "HIGH"
      direction   : dict  — {"USD": "BULLISH", "EUR": "BEARISH"}
      pairs_watch : list  — ["EUR/USD", "USD/JPY"]
      summary     : str   — short explanation
      urgency     : str   — "ACT NOW" / "MONITOR"
    """
    currencies = ", ".join(analysis.get("currencies", []))
    pairs      = "\n".join(
        [f"   • {p}" for p in analysis.get("pairs_watch", [])]
    )

    direction_lines = ""
    for cur, bias in analysis.get("direction", {}).items():
        emoji = "🟢" if "BULL" in bias.upper() else "🔴"
        direction_lines += f"   {emoji} {cur} → {bias}\n"

    msg = (
        f"🚨 <b>BREAKING NEWS ALERT</b>\n"
        f"{'─'*30}\n\n"
        f"📰 <b>Headline:</b>\n"
        f"   {headline}\n\n"
        f"💱 <b>Currencies Affected:</b> {currencies}\n\n"
        f"📊 <b>Impact:</b>\n"
        f"{direction_lines}\n"
        f"🎯 <b>Pairs to Watch:</b>\n{pairs}\n\n"
        f"🤖 <b>AI Summary:</b>\n"
        f"   {analysis.get('summary', '')}\n\n"
        f"⚡ <b>Action:</b> {analysis.get('urgency', 'MONITOR')}\n"
        f"⚠️  Always confirm PA on chart first!"
    )
    return send_message(msg)


def send_economic_surprise_alert(event: dict, analysis: dict) -> bool:
    """
    Economic calendar — Actual vs Forecast surprise alert.

    event dict keys:
      name      : str — "US Non-Farm Payrolls"
      time      : str — "18:30 UTC"
      currency  : str — "USD"
      forecast  : str — "180K"
      actual    : str — "303K"
      deviation : str — "+68%"
      beat_miss : str — "BEAT" or "MISS"

    analysis dict keys (same as breaking news):
      direction, pairs_watch, summary, urgency
    """
    beat_emoji = "✅" if event.get("beat_miss") == "BEAT" else "❌"
    pairs = "\n".join(
        [f"   • {p}" for p in analysis.get("pairs_watch", [])]
    )

    direction_lines = ""
    for cur, bias in analysis.get("direction", {}).items():
        emoji = "🟢" if "BULL" in bias.upper() else "🔴"
        direction_lines += f"   {emoji} {cur} → {bias}\n"

    msg = (
        f"🚨 <b>ECONOMIC SURPRISE ALERT</b>\n"
        f"{'─'*30}\n\n"
        f"📅 <b>Event:</b> {event.get('name', '')}\n"
        f"🕐 <b>Time:</b> {event.get('time', '')}\n"
        f"💱 <b>Currency:</b> {event.get('currency', '')}\n\n"
        f"📊 <b>Result:</b>\n"
        f"   Forecast:  <b>{event.get('forecast', '?')}</b>\n"
        f"   Actual:    <b>{event.get('actual', '?')}</b>\n"
        f"   Deviation: <b>{event.get('deviation', '?')} {event.get('beat_miss','')} {beat_emoji}</b>\n\n"
        f"📈 <b>Currency Impact:</b>\n"
        f"{direction_lines}\n"
        f"🎯 <b>Pairs to Watch:</b>\n{pairs}\n\n"
        f"🤖 <b>AI:</b> {analysis.get('summary', '')}\n\n"
        f"⚡ <b>Window:</b> {analysis.get('urgency', '15-30 min')}\n"
        f"⚠️  Always confirm PA on chart first!"
    )
    return send_message(msg)
