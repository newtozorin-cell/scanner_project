import pytz
from datetime import datetime
from data_feed import fetch_ohlcv
from indicators import detect_signal
from trade_logger import save_trade, build_trade_record, load_trades, update_trade_exit

IST = pytz.timezone("Asia/Kolkata")

# ============================================================
# STRATEGY: 5m entry (ATR trail1/trail2 crossover) + 15m-median SL/TP
#
# Locked from the 2017-2026 walk-forward backtest. This was the
# single best-performing combo tested (18/18 profitable OOS folds,
# ~163 pts/trade avg, best win rate and R:R of everything tried).
# fast/slow ATR params are the same locked pair used across all
# three symbols in the backtest -- do not tune these per-symbol.
# risk_pct = median MAE% of that symbol's OWN 15m-timeframe trades
# in the backtest, applied to the 5m entry price. Changing any of
# these numbers without re-running the WFO backtest invalidates the
# validated performance.
# ============================================================
STRATEGY = {
    "BANKNIFTY": {"fast": (5, 1.3), "slow": (20, 4.0), "risk_pct": 0.01080},
    "NIFTY50":   {"fast": (5, 1.3), "slow": (20, 4.0), "risk_pct": 0.00761},
    "SENSEX":    {"fast": (5, 1.3), "slow": (20, 4.0), "risk_pct": 0.00815},
}

ENTRY_INTERVAL = "5"  # Fyers resolution code (minutes)


def is_market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end   = now.replace(hour=15, minute=25, second=0, microsecond=0)
    return market_start <= now <= market_end


def already_logged(symbol, candle_time):
    trades = load_trades()
    trade_id = f"{symbol}_{candle_time.strftime('%Y%m%d%H%M')}"
    return any(t.get("id") == trade_id for t in trades)


def check_open_trades():
    """
    Before scanning for new signals, check existing OPEN trades against
    the latest 5m candle for a TP2 or SL hit and auto-close them.
    TP1 is informational only (not an exit level), matching the backtest
    engine exactly. Same-candle TP2+SL ambiguity resolves TP2-first,
    matching the backtest's tie-break rule.
    """
    trades = load_trades()
    open_trades = [t for t in trades if t.get("outcome") in (None, "OPEN")]
    if not open_trades:
        return

    by_symbol = {}
    for t in open_trades:
        by_symbol.setdefault(t["symbol"], []).append(t)

    for symbol, sym_trades in by_symbol.items():
        df = fetch_ohlcv(symbol, interval=ENTRY_INTERVAL, period_days=5)
        if df is None or df.empty:
            continue

        latest = df.iloc[-1]
        hi, lo = float(latest["High"]), float(latest["Low"])
        latest_time = df.index[-1]

        for t in sym_trades:
            try:
                entry_time = IST.localize(datetime.strptime(t["date"], "%d-%b-%Y %H:%M"))
            except Exception:
                continue
            if latest_time <= entry_time:
                continue  # don't judge the signal's own candle

            direction = t["direction"]
            sl, t2 = t["sl"], t["t2"]

            hit_sl  = (lo <= sl) if direction == "BUY" else (hi >= sl)
            hit_tp2 = (hi >= t2) if direction == "BUY" else (lo <= t2)

            if not (hit_sl or hit_tp2):
                continue

            exit_price = t2 if hit_tp2 else sl  # TP2-first on same-candle ambiguity
            updated = update_trade_exit(t["id"], exit_price)
            if updated:
                print(f"[EXIT] {symbol} {t['id']} {updated['outcome']} @ {exit_price} "
                      f"(pnl {updated['pnl']})")


def run_strategy():
    for symbol, params in STRATEGY.items():
        df = fetch_ohlcv(symbol, interval=ENTRY_INTERVAL, period_days=5)
        if df is None or df.empty:
            print(f"[SKIP] No data for {symbol}")
            continue

        print(f"[DEBUG] {symbol} — {len(df)} candles, last candle: {df.index[-1]}, close: {df['Close'].iloc[-1]}")

        fp, fm = params["fast"]
        sp, sm = params["slow"]
        risk_pct = params["risk_pct"]

        today = datetime.now(IST).date()
        today_indices = [i for i, t in enumerate(df.index) if t.date() == today]

        for i in today_indices:
            if i < max(sp, fp) * 3:
                continue

            candle_slice = df.iloc[:i + 1]
            candle_time  = df.index[i]

            if already_logged(symbol, candle_time):
                continue

            signal = detect_signal(candle_slice, fp, fm, sp, sm, risk_pct)

            if signal:
                trade = build_trade_record(symbol, signal, candle_time)
                save_trade(trade)
                print(f"[SIGNAL] {symbol} {signal['direction']} @ {signal['entry']} "
                      f"SL:{signal['sl']} T1:{signal['t1']} T2:{signal['t2']} candle:{candle_time}")
            else:
                print(f"[NO SIGNAL] {symbol} @ {candle_time}")


def run_all_scanners():
    """Entry point called by the scheduler (name kept for app.py compatibility)."""
    if not is_market_open():
        print("[SCANNER] Market closed, skipping.")
        return
    print(f"[SCANNER] Running at {datetime.now(IST).strftime('%H:%M:%S IST')}")
    check_open_trades()
    run_strategy()
