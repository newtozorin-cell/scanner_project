import json
import os
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")
TRADES_FILE = os.path.join(os.path.dirname(__file__), "trades.json")


def load_trades():
    if not os.path.exists(TRADES_FILE):
        return []
    with open(TRADES_FILE, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def save_trade(trade: dict):
    trades = load_trades()
    trades.append(trade)
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)


def build_trade_record(scanner, symbol, signal, candle_time):
    return {
        "id": f"{scanner}_{symbol}_{candle_time.strftime('%Y%m%d%H%M')}",
        "scanner": scanner,
        "date": candle_time.strftime("%d-%b-%Y %H:%M"),
        "symbol": symbol,
        "direction": signal["direction"],
        "grade": signal["grade"],
        "score": signal["score"],
        "entry": signal["entry"],
        "sl": signal["sl"],
        "t1": signal["t1"],
        "t2": signal["t2"],
        "rr": signal["rr"],
        "confidence": signal["confidence"],
        "adx": signal.get("adx"),
        "outcome": "OPEN",
        "exit": None,
        "pnl": None,
        "logged_at": datetime.now(IST).strftime("%d-%b-%Y %H:%M:%S")
    }
