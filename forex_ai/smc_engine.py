"""
smc_engine.py — Forex AI
Pure Python SMC Algorithm (Order Blocks + FVG) for pinpoint entries using yfinance data.
"""

import logging
import requests
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# SMC Configuration
RISK_REWARD_RATIO = 2.0  # 1:2 R:R
LOOKBACK_CANDLES = 100
MIN_FVG_SIZE_PIPS = 3.0  # FVG eka valid wenna ona minimum pips gana
SL_PADDING_PIPS = 2.0    # Stop loss eka order block eken wadiya thiya pips gana

def _get_pip_multiplier(pair: str) -> float:
    """Pair ekata anuwa pips ganan karana multiplier eka (JPY vs Others)."""
    return 100 if "JPY" in pair else 10000

def _get_pip_value(pair: str) -> float:
    """1 Pip eke agaya math_wise (e.g. 0.0001 or 0.01)."""
    return 0.01 if "JPY" in pair else 0.0001

def fetch_data(pair: str, timeframe: str = "1h", limit: int = LOOKBACK_CANDLES) -> pd.DataFrame:
    """Yahoo Finance API eken OHLCV data fetch karanna (without yfinance lib)."""
    try:
        yf_symbol = f"{pair.replace('/', '')}=X"
        
        valid_intervals = {"15m": "15m", "1h": "1h", "4h": "4h"}
        interval = valid_intervals.get(timeframe, "1h")
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?range=60d&interval={interval}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
        
        if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
            result = data["chart"]["result"][0]
            timestamps = result.get("timestamp", [])
            indicators = result.get("indicators", {}).get("quote", [{}])[0]
            
            opens = indicators.get("open", [])
            highs = indicators.get("high", [])
            lows = indicators.get("low", [])
            closes = indicators.get("close", [])
            volumes = indicators.get("volume", [])
            
            df = pd.DataFrame({
                "Open": opens,
                "High": highs,
                "Low": lows,
                "Close": closes,
                "Volume": volumes
            })
            
            df.dropna(inplace=True)
            return df.tail(limit).reset_index(drop=True)
            
        logger.error(f"No valid data returned for {pair} on {timeframe}")
        return None
        
    except Exception as e:
        logger.error(f"Yahoo API fetch error for {pair}: {e}")
        return None

def find_order_blocks(df: pd.DataFrame, pair: str) -> dict:
    """
    Bullish & Bearish Order Blocks (OB) hoyanna.
    Simplified version: 
    - Bullish OB = Last bearish candle before a strong bullish impulsive move.
    """
    if df is None or df.empty:
        return {"bullish": None, "bearish": None}
        
    bullish_obs = []
    bearish_obs = []
    
    pip_mult = _get_pip_multiplier(pair)
    
    # Calculate body size and direction
    df = df.copy()
    df['Body'] = abs(df['Close'] - df['Open'])
    df['Is_Bull'] = df['Close'] > df['Open']
    df['Is_Bear'] = df['Close'] < df['Open']
    
    avg_body = df['Body'].mean()
    
    # Simple OB Scanner
    for i in range(1, len(df) - 2):
        prev_candle = df.iloc[i-1]
        curr_candle = df.iloc[i]
        next_candle = df.iloc[i+1]
        
        # --- Bullish OB ---
        # Look for a small bearish candle followed by a large bullish engulfing/impulsive candle
        if prev_candle['Is_Bear'] and curr_candle['Is_Bull'] and next_candle['Is_Bull']:
            # Impulse check: Current + Next is significantly larger than prev
            impulse_size = next_candle['Close'] - curr_candle['Open']
            if impulse_size > (prev_candle['Body'] * 2) and impulse_size > avg_body:
                # OB is the prev_candle
                ob_high = prev_candle['High']
                ob_low = prev_candle['Low']
                bullish_obs.append({
                    'price_level': ob_high,  # Entry is usually at top of bearish candle
                    'sl_level': ob_low,      # SL below the OB low
                    'index': df.index[i-1]
                })
                
        # --- Bearish OB ---
        # Look for small bullish candle followed by large bearish impulsive drop
        if prev_candle['Is_Bull'] and curr_candle['Is_Bear'] and next_candle['Is_Bear']:
            impulse_size = curr_candle['Open'] - next_candle['Close']
            if impulse_size > (prev_candle['Body'] * 2) and impulse_size > avg_body:
                # OB is the prev_candle
                ob_low = prev_candle['Low']
                ob_high = prev_candle['High']
                bearish_obs.append({
                    'price_level': ob_low,   # Entry at bottom of bullish candle
                    'sl_level': ob_high,     # SL above OB high
                    'index': df.index[i-1]
                })

    # Return the most recent OBs
    recent_bull = bullish_obs[-1] if bullish_obs else None
    recent_bear = bearish_obs[-1] if bearish_obs else None
    
    return {"bullish": recent_bull, "bearish": recent_bear}

def find_fair_value_gaps(df: pd.DataFrame, pair: str) -> dict:
    """
    Fair Value Gaps (FVG) hoyanna.
    3 Candle pattern: Gap between C1 high/low and C3 low/high
    """
    if df is None or df.empty:
        return {"bullish": [], "bearish": []}

    bullish_fvgs = []
    bearish_fvgs = []
    
    pip_val = _get_pip_value(pair)
    min_gap = MIN_FVG_SIZE_PIPS * pip_val

    for i in range(2, len(df)):
        c1 = df.iloc[i-2]
        c2 = df.iloc[i-1] # The large impulse candle
        c3 = df.iloc[i]
        
        # --- Bullish FVG (Price moving UP, leaving a gap) ---
        # Gap is between C1 High and C3 Low
        if c3['Low'] > c1['High']:
            gap_size = c3['Low'] - c1['High']
            if gap_size >= min_gap:
                bullish_fvgs.append({
                    'top': c3['Low'],
                    'bottom': c1['High'],
                    'entry': c1['High'] + (gap_size/2), # Midpoint entry
                    'index': df.index[i-1]
                })
                
        # --- Bearish FVG (Price moving DOWN, leaving a gap) ---
        # Gap is between C1 Low and C3 High
        if c1['Low'] > c3['High']:
            gap_size = c1['Low'] - c3['High']
            if gap_size >= min_gap:
                bearish_fvgs.append({
                    'top': c1['Low'],
                    'bottom': c3['High'],
                    'entry': c3['High'] + (gap_size/2), # Midpoint
                    'index': df.index[i-1]
                })

    return {"bullish": bullish_fvgs[-3:], "bearish": bearish_fvgs[-3:]} # Return most recent 3

def generate_pinpoint_signal(pair: str, ai_direction: str, current_price: float) -> dict:
    """
    AI eken api gaththa BUY/SELL Bias ekai, SMC logic ekai mix karala
    Exact Entry, SL, TP heda gena denawa.
    """
    df = fetch_data(pair, timeframe="1h")
    if df is None:
        return None

    obs = find_order_blocks(df, pair)
    fvgs = find_fair_value_gaps(df, pair)
    
    pip_val = _get_pip_value(pair)
    sl_padding = SL_PADDING_PIPS * pip_val
    
    signal = None

    if ai_direction.upper() == "BUY":
        # Look for the nearest valid Bullish OB below current price
        valid_ob = obs["bullish"]
        if valid_ob and valid_ob['price_level'] < current_price:
            entry = float(valid_ob['price_level'])
            sl = float(valid_ob['sl_level'] - sl_padding)
            risk = entry - sl
            tp = entry + (risk * RISK_REWARD_RATIO)
            
            signal = {
                "pair": pair,
                "direction": "BUY",
                "entry_type": "Buy Limit (OB)",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "risk_reward": RISK_REWARD_RATIO
            }
            return signal
            
        # Fallback to FVG if no OB
        if fvgs["bullish"]:
             # get most recent
             recent_fvg = fvgs["bullish"][-1]
             if recent_fvg['entry'] < current_price:
                 entry = float(recent_fvg['entry'])
                 # For FVG, SL goes below the bottom of the gap with padding
                 sl = float(recent_fvg['bottom'] - sl_padding)
                 risk = entry - sl
                 tp = entry + (risk * RISK_REWARD_RATIO)
                 
                 signal = {
                    "pair": pair,
                    "direction": "BUY",
                    "entry_type": "Buy Limit (FVG)",
                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "tp": round(tp, 5),
                    "risk_reward": RISK_REWARD_RATIO
                }

    elif ai_direction.upper() == "SELL":
        valid_ob = obs["bearish"]
        if valid_ob and valid_ob['price_level'] > current_price:
            entry = float(valid_ob['price_level'])
            sl = float(valid_ob['sl_level'] + sl_padding)
            risk = sl - entry
            tp = entry - (risk * RISK_REWARD_RATIO)
            
            signal = {
                "pair": pair,
                "direction": "SELL",
                "entry_type": "Sell Limit (OB)",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "risk_reward": RISK_REWARD_RATIO
            }
            return signal
            
        if fvgs["bearish"]:
             recent_fvg = fvgs["bearish"][-1]
             if recent_fvg['entry'] > current_price:
                 entry = float(recent_fvg['entry'])
                 sl = float(recent_fvg['top'] + sl_padding)
                 risk = sl - entry
                 tp = entry - (risk * RISK_REWARD_RATIO)
                 
                 signal = {
                    "pair": pair,
                    "direction": "SELL",
                    "entry_type": "Sell Limit (FVG)",
                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "tp": round(tp, 5),
                    "risk_reward": RISK_REWARD_RATIO
                }

    if signal:
        # ----- NEW: AI Quality Filter -----
        logger.info(f"[{pair}] Math SMC setup found. Asking AI to evaluate the Trade Quality...")
        import analyzer
        # Combine macro with technical parameters
        prompt = f"""You are a top-tier quantitative Hedge Fund AI. 
A mathematical Trading algorithm has found the following Smart Money Concept (SMC) Setup:
- Pair: {pair}
- Direction: {signal['direction']}
- Entry Strategy: {signal['entry_type']}
- Entry Price: {signal['entry']}
- Stop Loss: {signal['sl']}
- Take Profit: {signal['tp']}

Given your understanding of current fundamental macroeconomic conditions and this precise technical setup, rate the quality/probability of this trade from 1 to 10.
Return your response in exact JSON:
{{
  "quality_score": 8,
  "reasoning": "Strong fundamentally backed direction aligning with a clean 1H FVG."
}}"""
        
        evaluation = analyzer._call_llm(prompt) # Assuming we can call the groq/azure model directly
        
        try:
            import json
            import re
            
            # Clean JSON
            clean_json = re.sub(r'```json\s*|\s*```', '', evaluation).strip()
            result = json.loads(clean_json)
            
            score = result.get("quality_score", 0)
            reason = result.get("reasoning", "No reason provided")
            
            logger.info(f"[{pair}] AI Quality Score: {score}/10 -> {reason}")
            
            # Add AI filter context to signal
            signal["ai_quality_score"] = score
            signal["ai_reasoning"] = reason
            
            # If the AI thinks this is a garbage setup despite the math, drop it.
            if score < 6:
                logger.warning(f"[{pair}] Dropping setup (Quality {score} < 6). Reason: {reason}")
                return None
                
        except Exception as e:
            logger.error(f"[{pair}] Failed to parse AI quality check: {e}")
            # If AI fails, we still return the mathematical signal to not block trades
            signal["ai_quality_score"] = "N/A"
            signal["ai_reasoning"] = "Qualitative AI check failed, relying purely on SMC Math."

    return signal

if __name__ == "__main__":
    # Test script locally
    logging.basicConfig(level=logging.INFO)
    print("Testing SMC Engine for EUR/USD ...")
    
    current = 1.0850 # mock
    print(f"Mock Current Price: {current}")
    
    buy_sig = generate_pinpoint_signal("EUR/USD", "BUY", current)
    print("SMC Buy Signal:", buy_sig)
    
    sell_sig = generate_pinpoint_signal("EUR/USD", "SELL", current)
    print("SMC Sell Signal:", sell_sig)
