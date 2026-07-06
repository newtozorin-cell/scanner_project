import pytz
from datetime import datetime
from data_feed import fetch_ohlcv, get_latest_candle_time
from indicators import detect_signal
from trade_logger import save_trade, build_trade_record, load_trades

IST = pytz.timezone("Asia/Kolkata")

# Scanner A config — NO ADX filter
SCANNER_A = {
    "BANKNIFTY": {"fast": (10, 0.7), "slow": (20, 3.5), "use_adx": False},
    "NIFTY50":   {"fast": (7,  0.7), "slow": (14, 3.5), "use_adx": False},
    "SENSEX":    {"fast": (7,  0.7), "slow": (14, 3.5), "use_adx": False},
}

# Scanner B config — ADX filter ON for all
SCANNER_B = {
    "BANKNIFTY": {"fast": (5, 1.5), "slow": (20, 4.0), "use_adx": True},
    "NIFTY50":   {"fast": (5, 1.5), "slow": (25, 4.0), "use_adx": True},
    "SENSEX":    {"fast": (5, 1.5), "slow": (25, 4.0), "use_adx": True},
}


def is_market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end   = now.replace(hour=15, minute=25, second=0, microsecond=0)
    return market_start <= now <= market_end


def already_logged(scanner, symbol, candle_time):
    trades = load_trades()
    trade_id = f"{scanner}_{symbol}_{candle_time.strftime('%Y%m%d%H%M')}"
    return any(t.get("id") == trade_id for t in trades)


def run_scanner(scanner_name, config):
    for symbol, params in config.items():
        df = fetch_ohlcv(symbol, interval="15", period_days=5)
        if df is None or df.empty:
            print(f"[SKIP] No data for {symbol}")
            continue

        print(f"[DEBUG] {scanner_name} {symbol} — {len(df)} candles, last candle: {df.index[-1]}, close: {df['Close'].iloc[-1]}")

        fp, fm = params["fast"]
        sp, sm = params["slow"]
        use_adx = params["use_adx"]

        # Scan every candle from today to catch all signals
        today = datetime.now(IST).date()
        today_indices = [i for i, t in enumerate(df.index) if t.date() == today]

        for i in today_indices:
            if i < max(sp, fp) * 3:
                continue

            candle_slice = df.iloc[:i+1]
            candle_time  = df.index[i]

            if already_logged(scanner_name, symbol, candle_time):
                print(f"[SKIP] Already logged {scanner_name} {symbol} @ {candle_time}")
                continue

            signal = detect_signal(candle_slice, fp, fm, sp, sm, use_adx=use_adx)

            if signal:
                # Use actual candle close as entry price
                signal["entry"] = round(float(df['Close'].iloc[i]), 2)
                trade = build_trade_record(scanner_name, symbol, signal, candle_time)
                save_trade(trade)
                print(f"[{scanner_name}] {symbol} {signal['direction']} Grade:{signal['grade']} Score:{signal['score']} @ {signal['entry']} candle:{candle_time}")
            else:
                print(f"[NO SIGNAL] {scanner_name} {symbol} @ {candle_time}")


def run_all_scanners():
    if not is_market_open():
        print("[SCANNER] Market closed, skipping.")
        return
    print(f"[SCANNER] Running at {datetime.now(IST).strftime('%H:%M:%S IST')}")
    run_scanner("A", SCANNER_A)
    run_scanner("B", SCANNER_B)
