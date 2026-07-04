import pandas as pd
import pytz
from datetime import datetime, timedelta
from fyers_auth import get_fyers_client

IST = pytz.timezone("Asia/Kolkata")

SYMBOLS = {
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "NIFTY50":   "NSE:NIFTY50-INDEX",
    "SENSEX":    "BSE:SENSEX-INDEX"
}

# Cache: key -> {"data": df, "fetched_at": datetime}
_cache = {}
CACHE_TTL_SECONDS = 60


def _is_cache_valid(key):
    if key not in _cache:
        return False
    age = (datetime.now(IST) - _cache[key]["fetched_at"]).total_seconds()
    return age < CACHE_TTL_SECONDS


def fetch_ohlcv(symbol, interval="15", period_days=5):
    fyers = get_fyers_client()
    if fyers is None:
        print("[AUTH] No valid token. Please login via dashboard.")
        return None

    cache_key = f"{symbol}_{interval}"
    if _is_cache_valid(cache_key):
        return _cache[cache_key]["data"]

    ticker = SYMBOLS.get(symbol)
    if not ticker:
        return None

    now = datetime.now(IST)
    date_from = (now - timedelta(days=period_days)).strftime("%Y-%m-%d")
    date_to   = now.strftime("%Y-%m-%d")

    # Fyers interval map: "15" = 15 min
    payload = {
        "symbol":     ticker,
        "resolution": interval,
        "date_format": "1",
        "range_from": date_from,
        "range_to":   date_to,
        "cont_flag":  "1"
    }

    try:
        resp = fyers.history(data=payload)
        if resp.get("s") != "ok":
            print(f"[DATA ERROR] {symbol}: {resp.get('message', 'Unknown error')}")
            return None

        candles = resp.get("candles", [])
        if not candles:
            return None

        df = pd.DataFrame(candles, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(IST)
        df.set_index("timestamp", inplace=True)
        df = df.between_time("09:15", "15:30")
        df = df.dropna()

        _cache[cache_key] = {"data": df, "fetched_at": datetime.now(IST)}
        return df

    except Exception as e:
        print(f"[DATA ERROR] {symbol} {interval}: {e}")
        return None


def get_latest_candle_time(symbol, interval="15"):
    df = fetch_ohlcv(symbol, interval)
    if df is None or df.empty:
        return None
    return df.index[-1]
