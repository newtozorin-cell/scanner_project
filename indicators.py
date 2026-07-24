import numpy as np


# ============================================================
# Exact port of the ATR-trailing-stop engine used in the WFO
# backtest (Wilder RMA seeded by simple mean, 4-branch trail).
# This is NOT the same as pandas .ewm(span=...) -- that was the
# bug in the old indicators.py that made live signals diverge
# from the backtested ones. Do not "simplify" this back to ewm.
# ============================================================

def _true_range(df):
    high = df['High'].values
    low = df['Low'].values
    close = df['Close'].values
    n = len(df)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return tr


def _rma(arr, period, n):
    """Wilder's RMA: seeded with simple mean of the first `period` values, then recursive."""
    a = np.zeros(n)
    if n < period:
        return a
    a[period - 1] = arr[:period].mean()
    for i in range(period, n):
        a[i] = (a[i - 1] * (period - 1) + arr[i]) / period
    return a


def _trail(close, atr_sl, n):
    t = np.zeros(n)
    t[0] = close[0]
    for i in range(1, n):
        sc, pt, ps = close[i], t[i - 1], close[i - 1]
        if sc > pt and ps > pt:
            t[i] = max(pt, sc - atr_sl[i])
        elif sc < pt and ps < pt:
            t[i] = min(pt, sc + atr_sl[i])
        elif sc > pt:
            t[i] = sc - atr_sl[i]
        else:
            t[i] = sc + atr_sl[i]
    return t


def compute_atr_trailing(df, fast_period, fast_mult, slow_period, slow_mult):
    n = len(df)
    close = df['Close'].values

    tr = _true_range(df)
    fast_atr = _rma(tr, fast_period, n) * fast_mult
    slow_atr = _rma(tr, slow_period, n) * slow_mult

    trail1 = _trail(close, fast_atr, n)
    trail2 = _trail(close, slow_atr, n)
    return trail1, trail2


def detect_signal(df, fast_period, fast_mult, slow_period, slow_mult, risk_pct):
    """
    Detects a trail1/trail2 crossover on the last (just-closed) candle of df.

    Entry  = close of the signal candle (5m).
    SL/TP1/TP2 use the LOCKED risk_pct (median MAE% derived from the
    15-minute timeframe's own trades across the 2017-2026 walk-forward
    backtest) -- NOT the live trail2 value. This is the "5m entry +
    15m SL/TP" combo that beat every other combo tested:
      SL  = entry -+ risk
      TP1 = entry +- 1.5 * risk   (informational only, not an exit)
      TP2 = entry +- 2.5 * risk   (actual profit target)
    risk_pct is fixed per symbol -- do not make it dynamic without
    re-running the WFO backtest, or live results will stop matching
    the validated numbers.
    """
    min_candles = max(slow_period, fast_period) * 3
    if len(df) < min_candles:
        return None

    trail1, trail2 = compute_atr_trailing(df, fast_period, fast_mult, slow_period, slow_mult)

    t1_curr, t1_prev = trail1[-1], trail1[-2]
    t2_curr, t2_prev = trail2[-1], trail2[-2]

    bull_cross = t1_curr > t2_curr and t1_prev <= t2_prev
    bear_cross = t1_curr < t2_curr and t1_prev >= t2_prev

    if not (bull_cross or bear_cross):
        return None

    direction = "BUY" if bull_cross else "SELL"
    entry = round(float(df['Close'].iloc[-1]), 2)

    risk = round(entry * risk_pct, 2)
    if risk <= 0:
        return None

    if direction == "BUY":
        sl = round(entry - risk, 2)
        t1 = round(entry + risk * 1.5, 2)
        t2 = round(entry + risk * 2.5, 2)
    else:
        sl = round(entry + risk, 2)
        t1 = round(entry - risk * 1.5, 2)
        t2 = round(entry - risk * 2.5, 2)

    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "t1": t1,
        "t2": t2,
        "risk": risk,
    }
