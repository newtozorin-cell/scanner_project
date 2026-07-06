import pandas as pd
import pytz
from datetime import datetime, timedelta
from fyers_auth import get_fyers_client

IST = pytz.timezone("Asia/Kolkata")

# NSE/BSE Trading Holidays 2026
HOLIDAYS_2026 = {
    datetime(2026, 1, 15).date(),
    datetime(2026, 1, 26).date(),
    datetime(2026, 3, 3).date(),
    datetime(2026, 3, 26).date(),
    datetime(2026, 3, 31).date(),
    datetime(2026, 4, 3).date(),
    datetime(2026, 4, 14).date(),
    datetime(2026, 5, 1).date(),
    datetime(2026, 5, 28).date(),
    datetime(2026, 6, 26).date(),
    datetime(2026, 9, 14).date(),
    datetime(2026, 10, 2).date(),
    datetime(2026, 10, 20).date(),
    datetime(2026, 11, 10).date(),
    datetime(2026, 11, 24).date(),
    datetime(2026, 12, 25).date(),
}


def is_trading_day(d):
    return d.weekday() < 5 and d not in HOLIDAYS_2026


def prev_trading_day(d):
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def last_tuesday_of_month(year, month):
    """Last Tuesday of given month."""
    # Start from last day of month
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    # Walk back to Tuesday (weekday=1)
    while last_day.weekday() != 1:
        last_day -= timedelta(days=1)
    return last_day


def last_thursday_of_month(year, month):
    """Last Thursday of given month."""
    if month == 12:
        last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)
    # Walk back to Thursday (weekday=3)
    while last_day.weekday() != 3:
        last_day -= timedelta(days=1)
    return last_day


def get_expiry(symbol, year, month):
    """Get expiry date for a futures contract, adjusted for holidays."""
    if symbol == "SENSEX":
        expiry = last_thursday_of_month(year, month)
    else:
        expiry = last_tuesday_of_month(year, month)

    # Shift to previous trading day if holiday
    while not is_trading_day(expiry):
        expiry = prev_trading_day(expiry)
    return expiry


def get_active_contract(symbol):
    """
    Returns the active futures contract month/year.
    If today is past expiry, roll to next month.
    """
    today = datetime.now(IST).date()
    year  = today.year
    month = today.month

    expiry = get_expiry(symbol, year, month)

    # If today is expiry day or past, use next month
    if today >= expiry:
        month += 1
        if month > 12:
            month = 1
            year += 1

    return year, month


def build_futures_symbol(symbol):
    """
    Build Fyers futures symbol string.
    Format: NSE:NIFTY25OCTFUT, NSE:BANKNIFTY25NOVFUT, BSE:SENSEX25AUGFUT
    """
    year, month = get_active_contract(symbol)
    month_str = datetime(year, month, 1).strftime("%b").upper()
    yy = str(year)[-2:]

    if symbol == "BANKNIFTY":
        return f"NSE:BANKNIFTY{yy}{month_str}FUT"
    elif symbol == "NIFTY50":
        return f"NSE:NIFTY{yy}{month_str}FUT"
    elif symbol == "SENSEX":
        return f"BSE:SENSEX{yy}{month_str}FUT"
    return None


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

    ticker = build_futures_symbol(symbol)
    if not ticker:
        print(f"[ERROR] Could not build futures symbol for {symbol}")
        return None

    print(f"[DATA] Fetching {ticker} ...")

    now       = datetime.now(IST)
    date_from = (now - timedelta(days=period_days)).strftime("%Y-%m-%d")
    date_to   = now.strftime("%Y-%m-%d")

    payload = {
        "symbol":      ticker,
        "resolution":  interval,
        "date_format": "1",
        "range_from":  date_from,
        "range_to":    date_to,
        "cont_flag":   "1"
    }

    try:
        resp = fyers.history(data=payload)
        if resp.get("s") != "ok":
            print(f"[DATA ERROR] {symbol} ({ticker}): {resp.get('message', 'Unknown error')}")
            return None

        candles = resp.get("candles", [])
        if not candles:
            print(f"[DATA ERROR] {symbol} ({ticker}): No candles returned")
            return None

        df = pd.DataFrame(candles, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(IST)
        df.set_index("timestamp", inplace=True)
        df = df.between_time("09:15", "15:30")
        df = df.dropna()

        print(f"[DATA] {symbol} ({ticker}): {len(df)} candles fetched, last close: {df['Close'].iloc[-1]}")

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
