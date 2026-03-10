"""
analyzer.py — Forex AI
GitHub Models (GPT-4o-mini) use karala news + calendar data analyze karanna.
Currency sentiment scores (-5 to +5) karana file meka.
"""

import json
import logging
import time

from openai import OpenAI

import config

logger = logging.getLogger(__name__)

# ── SETUP ─────────────────────────────────────────────────────────
# GitHub Models — free, works with Python 3.14
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=config.GITHUB_TOKEN,
)

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "NZD", "CHF"]


# ── DAILY SENTIMENT ANALYSIS ──────────────────────────────────────

def analyze_daily_sentiment(data: dict) -> dict:
    """
    Full day data analyze karanna — morning brief ekata use.
    Returns: currency_scores, drivers, market_mood, confidence, upcoming_events
    """
    headlines = data.get("headlines", [])
    events    = data.get("calendar_events", [])

    # Prompt build - Pass less headlines to save tokens
    headlines_text = "\n".join(
        [f"- [{h['source']}] {h['title']}" for h in headlines[:15]]
    )
    events_text = "\n".join(
        [
            f"- {e['time']} | {e['currency']} | {e['event']} "
            f"| F:{e['forecast']} P:{e['previous']} A:{e['actual']}"
            for e in events[:10]
        ]
    )

    prompt = f"""You are a quantitative forex strategy analyst. Extract the general daily bias for these currencies from the news.
    Do not hallucinate. If there's no clear news for a currency, default its score to 0.

RECENT HEADLINES:
{headlines_text if headlines_text else "No headlines available."}

ECONOMIC CALENDAR:
{events_text if events_text else "No scheduled events."}

Based on this data, provide your analysis in the following EXACT JSON format:
{{
  "currency_scores": {{
    "USD": 3.0,
    "EUR": -2.0,
    "GBP": 1.0,
    "JPY": -1.0,
    "AUD": 0.5,
    "CAD": 0.0,
    "NZD": -0.5,
    "CHF": 0.0
  }},

  "drivers": [
    "Fed hawkish tone supports USD",
    "EU PMI miss pressures EUR",
    "UK CPI beat boosts GBP"
  ],
  "market_mood": "risk-off",
  "confidence": 68,
  "upcoming_high_impact": [
    "16:30 USD - CPI y/y | F:3.1%",
    "19:00 GBP - Bank Rate Decision"
  ],
  "analysis_summary": "Brief 2-3 sentence market overview."
}}

Rules:
- Currency scores: -5 (very bearish) to +5 (very bullish), use decimals
- market_mood: one of: risk-on, risk-off, neutral, mixed
- confidence: 0-100 integer (your confidence in this analysis)
- Return ONLY valid JSON, no extra text"""

    return _call_ai_with_retry(prompt, expected_key="currency_scores")


def analyze_breaking_news(headline: str, summary: str = "") -> dict:
    """
    Single breaking news headline analyze karanna.
    Real-time alert ekata use.
    """
    prompt = f"""You are a forex market analyst. Analyze this breaking financial headline for forex trading impact.

HEADLINE: {headline}
SUMMARY: {summary[:500] if summary else "N/A"}

Return ONLY valid JSON in this exact format:
{{
  "is_forex_relevant": true,
  "impact_level": "HIGH",
  "currencies": ["USD", "EUR"],
  "direction": {{
    "USD": "BULLISH",
    "EUR": "BEARISH"
  }},
  "pairs_watch": ["EUR/USD", "USD/JPY"],
  "summary": "Fed rate hike signals strengthen USD, pressure EUR.",
  "urgency": "ACT NOW - major market mover"
}}

Rules:
- impact_level: HIGH, MEDIUM, or LOW only
- Only respond with HIGH or MEDIUM relevant events for forex
- direction values: BULLISH, BEARISH, or NEUTRAL
- If not forex relevant or LOW impact, set is_forex_relevant: false
- Return ONLY valid JSON"""

    result = _call_ai_with_retry(prompt, expected_key="is_forex_relevant")
    return result


def analyze_economic_surprise(event: dict) -> dict:
    """
    Economic calendar surprise event analyze karanna.
    Actual vs Forecast data pass karagena currency impact get.
    """
    prompt = f"""You are a forex market analyst. An economic data release just beat/missed expectations.

EVENT: {event.get('event', '')}
CURRENCY: {event.get('currency', '')}
FORECAST: {event.get('forecast', '')}
ACTUAL: {event.get('actual', '')}
DEVIATION: {event.get('deviation', '')} ({event.get('beat_miss', '')})

Analyze the forex market impact. Return ONLY valid JSON:
{{
  "direction": {{
    "USD": "BULLISH"
  }},
  "pairs_watch": ["EUR/USD", "USD/JPY"],
  "summary": "NFP massive beat delays Fed rate cuts, strongly bullish USD.",
  "urgency": "15-30 min trading window open"
}}

Rules:
- Only include affected currencies in direction
- pairs_watch: top 2-3 pairs that will be most impacted
- summary: 1-2 sentences, clear and actionable
- Return ONLY valid JSON"""

    return _call_ai_with_retry(prompt, expected_key="direction")


# ── AI CALL WITH RETRY ────────────────────────────────────────────

def _call_ai_with_retry(prompt: str, expected_key: str, retries: int = 3) -> dict:
    """
    GitHub Models API call with retry logic.
    """
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=config.AI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional forex market analyst. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1500,
            )

            text = response.choices[0].message.content.strip()

            # Clean markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            result = json.loads(text)

            if expected_key not in result:
                raise ValueError(f"Expected key '{expected_key}' missing in response")

            logger.info(f"AI analysis OK (attempt {attempt+1})")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"AI JSON parse error (attempt {attempt+1}): {e}")
        except Exception as e:
            err_str = str(e)
            logger.error(f"AI API error (attempt {attempt+1}): {err_str[:300]}")

            is_rate_limit = "429" in err_str or "rate" in err_str.lower()
            if is_rate_limit:
                logger.warning("Rate limit — waiting 30s...")
                time.sleep(30)
            else:
                time.sleep(3)

        if attempt < retries - 1:
            time.sleep(2)

    logger.error("AI analysis failed after all retries.")
    return {}


# ── Quick Test ────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    dummy_data = {
        "headlines": [
            {"source": "Reuters", "title": "Fed signals two more rate hikes despite cooling inflation"},
            {"source": "ForexLive", "title": "EUR/USD drops as ECB concerns over growth mount"},
            {"source": "MarketWatch", "title": "US jobs data beats forecast by wide margin"},
        ],
        "calendar_events": [],
    }

    print("Testing GitHub Models AI analysis...")
    result = analyze_daily_sentiment(dummy_data)
    if result:
        print("\nCurrency Scores:")
        for cur, score in result.get("currency_scores", {}).items():
            bar = "🟢" if score > 0 else "🔴"
            print(f"  {bar} {cur}: {score:+.1f}")
        print(f"\nMood: {result.get('market_mood')}")
        print(f"Confidence: {result.get('confidence')}%")
    else:
        print("Analysis failed — check GITHUB_TOKEN in config.py")
