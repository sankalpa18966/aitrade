"""
tracker.py — Forex AI
SMC signals database eke save karala SL/TP hit wunada kiyala check karana (Win Rate Tracker) script eka.
"""

import logging
import requests
import time
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = "trades.db"

def init_db():
    """Database saha tables hadanna."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            pair TEXT,
            direction TEXT,
            entry_price REAL,
            sl REAL,
            tp REAL,
            status TEXT,   -- PENDING, ACTIVE, WON, LOST, CANCELLED
            close_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_signal(pair: str, direction: str, entry: float, sl: float, tp: float) -> int:
    """Aluth signal ekak DB eke save karanna. Returns trade ID."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    timestamp = datetime.now(timezone.utc).isoformat()
    status = "PENDING"
    
    c.execute('''
        INSERT INTO trades (timestamp, pair, direction, entry_price, sl, tp, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp, pair, direction, entry, sl, tp, status))
    
    trade_id = c.lastrowid
    conn.commit()
    conn.close()
    
    logger.info(f"Signal saved to DB: #{trade_id} {direction} {pair} @ {entry}")
    return trade_id

def _get_current_price(pair: str) -> float:
    """Yahoo Finance API eken current live price eka ganna (without yfinance library)."""
    try:
        yf_symbol = f"{pair.replace('/', '')}=X"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?range=1d&interval=1m"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if "chart" in data and "result" in data["chart"] and data["chart"]["result"]:
            result = data["chart"]["result"][0]
            if "indicators" in result and "quote" in result["indicators"]:
                closes = result["indicators"]["quote"][0]["close"]
                # Find the last non-null close price
                for price in reversed(closes):
                    if price is not None:
                         return float(price)
        return None
    except Exception as e:
        logger.error(f"Error fetching current price for {pair}: {e}")
        return None

def update_pending_and_active_trades():
    """
    PENDING/ACTIVE trades yfinance live price ekka check karala update karanna.
    - PENDING -> Price entry ekata aawoth -> ACTIVE
    - ACTIVE -> Price SL hit wunoth -> LOST
    - ACTIVE -> Price TP hit wunoth -> WON
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT id, pair, direction, entry_price, sl, tp, status, timestamp FROM trades WHERE status IN ('PENDING', 'ACTIVE')")
    open_trades = c.fetchall()
    
    if not open_trades:
        conn.close()
        return

    now = datetime.now(timezone.utc).isoformat()
    
    for trade in open_trades:
        trade_id, pair, direction, entry, sl, tp, status, timestamp_str = trade
        
        current_price = _get_current_price(pair)
        if not current_price:
            continue
            
        new_status = status
        
        if status == "PENDING":
             # Check if trade is older than 24 hours (Order Expiry)
             try:
                 trade_time = datetime.fromisoformat(timestamp_str)
                 hours_passed = (datetime.now(timezone.utc) - trade_time).total_seconds() / 3600
                 if hours_passed >= 24:
                     new_status = "EXPIRED"
                     logger.info(f"Trade #{trade_id} {pair}: PENDING -> EXPIRED (>24h)")
                     import telegram_bot
                     telegram_bot.send_telegram_message(f"⚠️ <b>Order Expired</b>\n\nLimit Order for {pair} ({direction}) has been pending > 24 hours without triggering.\nOrder has been cancelled.")
             except Exception as e:
                 logger.error(f"Error parsing date {timestamp_str}: {e}")
             
             if new_status == "PENDING":
                 # Price Entry ekata awithda balamu
                 if direction == "BUY" and current_price <= entry:
                     new_status = "ACTIVE"
                     logger.info(f"Trade #{trade_id} {pair}: PENDING -> ACTIVE (Price: {current_price})")
                     import telegram_bot
                     telegram_bot.send_telegram_message(f"⚡ <b>Order Activated!</b>\n\n{pair} ({direction}) limit entry at {entry} has been triggered by the market.")
                 elif direction == "SELL" and current_price >= entry:
                     new_status = "ACTIVE"
                     logger.info(f"Trade #{trade_id} {pair}: PENDING -> ACTIVE (Price: {current_price})")
                     import telegram_bot
                     telegram_bot.send_telegram_message(f"⚡ <b>Order Activated!</b>\n\n{pair} ({direction}) limit entry at {entry} has been triggered by the market.")
         
        elif status == "ACTIVE":
             # SL ho TP hit welaada balamu
             if direction == "BUY":
                 if current_price <= sl:
                     new_status = "LOST"
                 elif current_price >= tp:
                     new_status = "WON"
             
             elif direction == "SELL":
                 if current_price >= sl:
                     new_status = "LOST"
                 elif current_price <= tp:
                     new_status = "WON"
                     
             if new_status != "ACTIVE":
                 logger.info(f"Trade #{trade_id} {pair}: ACTIVE -> {new_status} (Price: {current_price})")
                 c.execute("UPDATE trades SET status = ?, close_time = ? WHERE id = ?", (new_status, now, trade_id))
                 
        if new_status == "ACTIVE" and status == "PENDING":
             c.execute("UPDATE trades SET status = ? WHERE id = ?", (new_status, trade_id))

    conn.commit()
    conn.close()

def get_win_rate_stats() -> dict:
    """
    DB eken total wins/losses aran win rate eka calculate karanna.
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM trades WHERE status = 'WON'")
    wins = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM trades WHERE status = 'LOST'")
    losses = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM trades WHERE status IN ('PENDING', 'ACTIVE')")
    open_trades = c.fetchone()[0]
    
    conn.close()
    
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
    
    return {
        "wins": wins,
        "losses": losses,
        "total_closed": total_closed,
        "win_rate": round(win_rate, 1),
        "open_trades": open_trades
    }

def has_open_trade(pair: str) -> bool:
    """Ekama pair ekata aluthin thawa trade ekak dana eka nawaththanna (Risk Management)."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM trades WHERE pair = ? AND status IN ('PENDING', 'ACTIVE')", (pair,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

# Run DB init on import
init_db()

if __name__ == "__main__":
    # Test script
    print("Testing Tracker DB...")
    save_signal("EUR/USD", "BUY", 1.0850, 1.0800, 1.0950)
    stats = get_win_rate_stats()
    print("Stats:", stats)
    
    print("\nFetching Live EUR/USD price to test update...")
    update_pending_and_active_trades()
