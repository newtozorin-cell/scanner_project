import json
import os
import threading
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")
TRADES_FILE = os.path.join(os.path.dirname(__file__), "trades.json")

# Guards every trades.json read-modify-write cycle. Without this, the
# scheduler thread and a manual /api/run click can race: both read the
# same file, both write back, and whichever writes last silently wipes
# out the other's trade. --workers 1 --threads 2 in the Procfile means
# this WILL happen eventually without a lock.
_trades_lock = threading.Lock()


def load_trades():
    if not os.path.exists(TRADES_FILE):
        return []
    with open(TRADES_FILE, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def replace_trades(trades: list):
    """Overwrite the trades file with the provided list (used for backup restore)."""
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)


def export_backup(backup_path: str = None) -> str:
    """Save current trades to a JSON backup file. Returns the backup file path."""
    if backup_path is None:
        ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(os.path.dirname(__file__), f"trades_backup_{ts}.json")
    with _trades_lock:
        trades = load_trades()
        with open(backup_path, "w") as f:
            json.dump(trades, f, indent=2, default=str)
    return backup_path


def import_backup(backup_path: str) -> int:
    """Load trades from a backup JSON file and replace current trades. Returns count loaded."""
    with open(backup_path, "r") as f:
        trades = json.load(f)
    if not isinstance(trades, list):
        raise ValueError("Backup file must contain a JSON list of trades.")
    with _trades_lock:
        replace_trades(trades)
    return len(trades)


def save_trade(trade: dict):
    with _trades_lock:
        trades = load_trades()
        # Insert at the top so latest trades appear first
        trades.insert(0, trade)
        with open(TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2, default=str)


def update_trade_exit(trade_id: str, exit_price: float) -> dict:
    """Update exit price, calc P&L, and save. Returns updated trade or None."""
    with _trades_lock:
        trades = load_trades()
        for t in trades:
            if t["id"] == trade_id:
                t["exit"] = exit_price
                if t["direction"] == "BUY":
                    pnl = round(exit_price - t["entry"], 2)
                else:
                    pnl = round(t["entry"] - exit_price, 2)
                t["pnl"] = pnl
                t["outcome"] = "PROFIT" if pnl >= 0 else "LOSS"
                replace_trades(trades)
                return t
        return None


def build_trade_record(symbol, signal, candle_time):
    return {
        "id": f"{symbol}_{candle_time.strftime('%Y%m%d%H%M')}",
        "strategy": "5m entry + 15m SL/TP",
        "date": candle_time.strftime("%d-%b-%Y %H:%M"),
        "symbol": symbol,
        "direction": signal["direction"],
        "entry": signal["entry"],
        "sl": signal["sl"],
        "t1": signal["t1"],
        "t2": signal["t2"],
        "risk": signal["risk"],
        "outcome": "OPEN",
        "exit": None,
        "pnl": None,
        "logged_at": datetime.now(IST).strftime("%d-%b-%Y %H:%M:%S")
    }
