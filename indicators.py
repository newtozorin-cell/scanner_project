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
    close = df['Close']

    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    mask = plus_dm > minus_dm
    minus_dm[mask] = 0
    mask2 = minus_dm >= plus_dm
    plus_dm[mask2] = 0

    atr = compute_atr(df, period)
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx, plus_di, minus_di


def detect_signal(df, fast_period, fast_mult, slow_period, slow_mult, use_adx=False, adx_period=14):
    if len(df) < max(slow_period, fast_period) * 3:
        return None

    fast_trail, fast_atr = compute_atr_trail(df, fast_period, fast_mult)
    slow_trail, slow_atr = compute_atr_trail(df, slow_period, slow_mult)

    close = df['Close']
    prev_close = close.iloc[-2]
    curr_close = close.iloc[-1]

    prev_fast = fast_trail.iloc[-2]
    curr_fast = fast_trail.iloc[-1]
    prev_slow = slow_trail.iloc[-2]
    curr_slow = slow_trail.iloc[-1]

    # Direction
    fast_bull = curr_close > curr_fast
    fast_bear = curr_close < curr_fast
    slow_bull = curr_close > curr_slow
    slow_bear = curr_close < curr_slow

    # Crossover on fast trail
    prev_fast_bull = prev_close > prev_fast
    prev_fast_bear = prev_close < prev_fast

    bull_cross = fast_bull and not prev_fast_bull
    bear_cross = fast_bear and not prev_fast_bear

    if not (bull_cross or bear_cross):
        return None

    direction = "BUY" if bull_cross else "SELL"

    # Both trails must agree
    if direction == "BUY" and not slow_bull:
        return None
    if direction == "SELL" and not slow_bear:
        return None

    # ADX filter for Scanner B
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

    slow_dist = abs(curr_close - curr_slow) / slow_atr.iloc[-1] if slow_atr.iloc[-1] > 0 else 0
    slow_score = min(slow_dist * 30, 30)

    score = round(trail_score + slow_score + (adx_score * 0.3), 1)
    score = min(score, 100)

    # Grade
    if score >= 85:
        grade = "A+"
    elif score >= 70:
        grade = "A"
    elif score >= 55:
        grade = "B"
    else:
        grade = "C"

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

    # Entry, SL, Targets
    entry = round(curr_close, 2)
    sl = round(curr_fast, 2) if direction == "BUY" else round(curr_fast, 2)
    risk = abs(entry - sl)

    t1 = round(entry + risk * 1.5, 2) if direction == "BUY" else round(entry - risk * 1.5, 2)
    t2 = round(entry + risk * 3.0, 2) if direction == "BUY" else round(entry - risk * 3.0, 2)
    rr = round((t1 - entry) / risk, 2) if risk > 0 else 0
    rr = abs(rr)

    return {
        "direction": direction,
        "grade": grade,
        "score": score,
        "entry": entry,
        "sl": sl,
        "t1": t1,
        "t2": t2,
        "rr": rr,
        "confidence": confidence,
        "adx": round(adx_val, 2) if adx_val is not None else None
    }
