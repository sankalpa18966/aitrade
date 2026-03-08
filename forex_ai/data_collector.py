"""
data_collector.py — Forex AI
Multiple RSS sources + ForexFactory economic calendar fetch karanna.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import feedparser
import requests

import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# ── HELPERS ───────────────────────────────────────────────────────

def _clean_html(text: str) -> str:
    """HTML tags remove karanna."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _keyword_hit(text: str) -> bool:
    """High-impact keyword eka headline eke thiyenawaada check."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in config.HIGH_IMPACT_KEYWORDS)


# ── RSS NEWS ──────────────────────────────────────────────────────

def fetch_rss_headlines(max_per_feed: int = 6) -> list[dict]:
    """
    Config eke RSS_FEEDS eke inna eka eka feed fetch karanna.
    Returns list of dicts: {title, summary, source, url, published}
    """
    all_headlines = []

    for feed_url in config.RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                if count >= max_per_feed:
                    break
                title   = _clean_html(entry.get("title", ""))
                summary = _clean_html(entry.get("summary", entry.get("description", "")))
                url     = entry.get("link", "")
                pub     = entry.get("published", "")

                if not title:
                    continue

                all_headlines.append({
                    "title"    : title,
                    "summary"  : summary[:300],
                    "source"   : feed.feed.get("title", feed_url),
                    "url"      : url,
                    "published": pub,
                    "is_high_impact": _keyword_hit(title + " " + summary),
                })
                count += 1

            logger.info(f"RSS {feed_url} → {count} headlines")
        except Exception as e:
            logger.error(f"RSS fetch error ({feed_url}): {e}")
            continue

    # Newest bangal first (published field nathnam order as-is)
    return all_headlines


def fetch_recent_high_impact_news(hours: float = None) -> list[dict]:
    """
    Only HIGH IMPACT keyword headlines fetch.
    Breaking news detection ekata use karanna.
    """
    if hours is None:
        hours = config.NEWS_LOOKBACK_HOURS

    all_news = fetch_rss_headlines(max_per_feed=10)
    return [n for n in all_news if n["is_high_impact"]]


# ── FOREX FACTORY CALENDAR ────────────────────────────────────────

def fetch_forexfactory_calendar() -> list[dict]:
    """
    ForexFactory economic calendar today + tomorrow fetch.
    Returns list: {time, currency, event, impact, forecast, previous}
    """
    events = []

    # ForexFactory has todayish JSON data at this URL
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        today_str    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tomorrow_str = datetime.now(timezone.utc).replace(
            day=datetime.now(timezone.utc).day + 1
        ).strftime("%Y-%m-%d")

        for item in data:
            event_date = item.get("date", "")[:10]
            if event_date not in (today_str, tomorrow_str):
                continue

            impact = item.get("impact", "").upper()
            if impact not in ("HIGH", "MEDIUM"):
                continue  # Low impact events skip

            events.append({
                "date"    : item.get("date", ""),
                "time"    : item.get("time", ""),
                "currency": item.get("country", ""),
                "event"   : item.get("title", ""),
                "impact"  : impact,
                "forecast": item.get("forecast", ""),
                "previous": item.get("previous", ""),
                "actual"  : item.get("actual", ""),   # Release wenakota fill wevaa
            })

        logger.info(f"ForexFactory → {len(events)} HIGH/MEDIUM events")
    except Exception as e:
        logger.error(f"ForexFactory fetch error: {e}")

    return events


# ── ECONOMIC SURPRISE DETECTION ───────────────────────────────────

def detect_economic_surprise(events: list[dict]) -> list[dict]:
    """
    Released events (actual filled) compare with forecast.
    Threshold config.SURPRISE_THRESHOLD_PCT pass wunotha surprise list eke add.
    Returns list of surprise dicts.
    """
    surprises = []
    for ev in events:
        actual   = ev.get("actual", "").strip()
        forecast = ev.get("forecast", "").strip()

        if not actual or not forecast:
            continue  # Actual still not released

        try:
            # Numbers parse: "303K" → 303000, "2.3%" → 2.3 etc.
            actual_val   = _parse_value(actual)
            forecast_val = _parse_value(forecast)

            if forecast_val == 0:
                continue

            deviation_pct = ((actual_val - forecast_val) / abs(forecast_val)) * 100

            if abs(deviation_pct) < config.SURPRISE_THRESHOLD_PCT:
                continue  # Not significant

            beat_miss = "BEAT" if actual_val > forecast_val else "MISS"

            surprises.append({
                **ev,
                "deviation": f"{deviation_pct:+.1f}%",
                "beat_miss": beat_miss,
            })
            logger.info(
                f"Surprise detected: {ev['event']} "
                f"| {forecast} → {actual} ({deviation_pct:+.1f}%)"
            )
        except Exception:
            continue

    return surprises


def _parse_value(text: str) -> float:
    """'303K' → 303000 | '2.3%' → 2.3 | '-1.2B' → -1200000000"""
    text = text.replace(",", "").strip()
    multiplier = 1.0
    if text.upper().endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    elif text.upper().endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.upper().endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]
    text = text.replace("%", "")
    return float(text) * multiplier


# ── MASTER COLLECT ────────────────────────────────────────────────

def collect_all_data() -> dict:
    """
    Hama data ekama collect karanna — main.py + scheduler.py meka call karana.
    Returns combined dict.
    """
    print("[DataCollector] Fetching news and calendar...")

    headlines = fetch_rss_headlines()
    events    = fetch_forexfactory_calendar()
    surprises = detect_economic_surprise(events)

    result = {
        "timestamp"        : datetime.now(timezone.utc).isoformat(),
        "headlines"        : headlines,
        "calendar_events"  : events,
        "surprises"        : surprises,
        "high_impact_news" : [h for h in headlines if h["is_high_impact"]],
    }

    print(f"[DataCollector] Headlines: {len(headlines)}, "
          f"Events: {len(events)}, "
          f"Surprises: {len(surprises)}, "
          f"High-impact news: {len(result['high_impact_news'])}")

    return result


# ── SEEN CACHE (Duplicate Prevention) ────────────────────────────

def load_seen_cache() -> set:
    try:
        with open(config.NEWS_CACHE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen_cache(seen: set):
    try:
        # Keep only last 500 URLs to prevent file bloat
        seen_list = list(seen)[-500:]
        with open(config.NEWS_CACHE, "w") as f:
            json.dump(seen_list, f)
    except Exception as e:
        logger.error(f"Cache save error: {e}")


def get_new_headlines_only(headlines: list[dict]) -> list[dict]:
    """Already sent news filter out karanna — duplicates avoid."""
    seen = load_seen_cache()
    new_ones = [h for h in headlines if h["url"] not in seen]
    # Mark as seen
    for h in new_ones:
        seen.add(h["url"])
    save_seen_cache(seen)
    return new_ones


# ── Quick Test ────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = collect_all_data()
    print("\n── First 3 Headlines ──")
    for h in data["headlines"][:3]:
        print(f"  [{h['source']}] {h['title']}")
    print("\n── Upcoming High/Medium Events ──")
    for e in data["calendar_events"][:5]:
        print(f"  {e['time']} | {e['currency']} | {e['event']} | Impact: {e['impact']}")
    print("\n── Surprises ──")
    for s in data["surprises"]:
        print(f"  {s['event']} → {s['beat_miss']} {s['deviation']}")
