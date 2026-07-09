import pandas as pd
import numpy as np


def compute_atr(df, period):
    high = df['High']
    low = df['Low']
    close = df['Close']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr


def compute_atr_trail(df, period, multiplier):
    atr = compute_atr(df, period)
    close = df['Close']
    trail = pd.Series(index=df.index, dtype=float)
    trail.iloc[0] = close.iloc[0]

    for i in range(1, len(df)):
        prev_trail = trail.iloc[i - 1]
        curr_close = close.iloc[i]
        curr_atr = atr.iloc[i]
        stop = curr_atr * multiplier

        if curr_close > prev_trail:
            trail.iloc[i] = max(prev_trail, curr_close - stop)
        elif curr_close < prev_trail:
            trail.iloc[i] = min(prev_trail, curr_close + stop)
        else:
            trail.iloc[i] = prev_trail

    return trail, atr


def compute_adx(df, period=14):
    high = df['High']
    low = df['Low']

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.clip(lower=0)
    minus_dm = minus_dm.clip(lower=0)

    # Where minus > plus, zero out plus and vice versa
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm <= plus_dm] = 0

    atr = compute_atr(df, period)
    plus_di  = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx, plus_di, minus_di


def detect_signal(df, fast_period, fast_mult, slow_period, slow_mult, use_adx=False, adx_period=14):
    min_candles = max(slow_period, fast_period) * 3
    if len(df) < min_candles:
        return None

    fast_trail, fast_atr = compute_atr_trail(df, fast_period, fast_mult)
    slow_trail, slow_atr = compute_atr_trail(df, slow_period, slow_mult)

    close = df['Close']

    curr_close = close.iloc[-1]
    prev_close = close.iloc[-2]

    curr_fast = fast_trail.iloc[-1]
    prev_fast = fast_trail.iloc[-2]

    curr_slow = slow_trail.iloc[-1]

    # Fast trail crossover
    curr_above_fast = curr_close > curr_fast
    prev_above_fast = prev_close > prev_fast

    bull_cross = curr_above_fast and not prev_above_fast
    bear_cross = not curr_above_fast and prev_above_fast

    if not (bull_cross or bear_cross):
        return None

    direction = "BUY" if bull_cross else "SELL"

    # Slow trail must agree with direction
    if direction == "BUY" and curr_close <= curr_slow:
        return None
    if direction == "SELL" and curr_close >= curr_slow:
        return None

    # ADX filter
    if use_adx:
        adx, plus_di, minus_di = compute_adx(df, adx_period)
        adx_val = adx.iloc[-1]
        if adx_val <= 20:
            return None
        adx_score = min((adx_val - 20) / 30 * 100, 100)
    else:
        adx_val = None
        adx_score = 50

    # Scoring
    atr_val = fast_atr.iloc[-1]
    trail_dist = abs(curr_close - curr_fast) / atr_val if atr_val > 0 else 0
    trail_score = min(trail_dist * 50, 40)

    slow_atr_val = slow_atr.iloc[-1]
    slow_dist = abs(curr_close - curr_slow) / slow_atr_val if slow_atr_val > 0 else 0
    slow_score = min(slow_dist * 30, 30)

    score = round(trail_score + slow_score + (adx_score * 0.3), 1)
    score = min(score, 100)

    # Grade
    if score >= 85:
        grade = "A+"
    elif score >= 70:
        grade = "A"
    else:
        return None  # Filter out Grade B and C trades

    # Confidence
    if score >= 85:
        confidence = round(80 + (score - 85) * 1.3, 1)
    elif score >= 70:
        confidence = round(65 + (score - 70) * 1.0, 1)
    elif score >= 55:
        confidence = round(50 + (score - 55) * 1.0, 1)
    else:
        confidence = round(30 + score * 0.3, 1)
    confidence = min(confidence, 99)

    # Entry = close of signal candle, SL = fast trail
    entry = round(curr_close, 2)
    sl    = round(curr_fast, 2)
    risk  = abs(entry - sl)

    if risk == 0:
        return None

    t1 = round(entry + risk * 1.5, 2) if direction == "BUY" else round(entry - risk * 1.5, 2)
    t2 = round(entry + risk * 3.0, 2) if direction == "BUY" else round(entry - risk * 3.0, 2)
    rr = 1.5

    return {
        "direction":  direction,
        "grade":      grade,
        "score":      score,
        "entry":      entry,
        "sl":         sl,
        "t1":         t1,
        "t2":         t2,
        "rr":         rr,
        "confidence": confidence,
        "adx":        round(adx_val, 2) if adx_val is not None else None
    }
