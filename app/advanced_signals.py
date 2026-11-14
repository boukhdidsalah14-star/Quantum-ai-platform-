"""Multi-factor, regime-aware candle analysis for QUANTUM AI.

Deterministic research engine; no broker execution and no claimed win-rate.
Input candles must be completed OHLC bars from a trusted feed. Confidence is a
confluence score, not a calibrated probability of profit.
"""
from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev
from typing import Any


def _ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1.0)
    out = [mean(values[:period])]
    for value in values[period:]:
        out.append(alpha * value + (1.0 - alpha) * out[-1])
    return [float("nan")] * (period - 1) + out


def _rsi(values: list[float], period: int = 14) -> float:
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    if len(changes) < period:
        return 50.0
    gains = [max(x, 0.0) for x in changes]
    losses = [max(-x, 0.0) for x in changes]
    avg_gain, avg_loss = mean(gains[:period]), mean(losses[:period])
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _atr(candles: list[dict[str, Any]], period: int = 14) -> float:
    trs = []
    for i, c in enumerate(candles):
        high, low = float(c["high"]), float(c["low"])
        prev = float(candles[i - 1]["close"]) if i else float(c["close"])
        trs.append(max(high - low, abs(high - prev), abs(low - prev)))
    if not trs:
        return 0.0
    value = mean(trs[:period])
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def _adx(candles: list[dict[str, Any]], period: int = 14) -> float:
    if len(candles) < period * 2 + 1:
        return 0.0
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, len(candles)):
        cur, prev = candles[i], candles[i - 1]
        up = float(cur["high"]) - float(prev["high"])
        down = float(prev["low"]) - float(cur["low"])
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(float(cur["high"]) - float(cur["low"]),
                       abs(float(cur["high"]) - float(prev["close"])),
                       abs(float(cur["low"]) - float(prev["close"]))))
    smooth_tr = sum(trs[:period])
    smooth_p, smooth_m = sum(plus_dm[:period]), sum(minus_dm[:period])
    dx = []
    for i in range(period, len(trs)):
        if i > period:
            smooth_tr = smooth_tr - smooth_tr / period + trs[i]
            smooth_p = smooth_p - smooth_p / period + plus_dm[i]
            smooth_m = smooth_m - smooth_m / period + minus_dm[i]
        if smooth_tr <= 0:
            dx.append(0.0)
        else:
            pdi, mdi = 100 * smooth_p / smooth_tr, 100 * smooth_m / smooth_tr
            dx.append(100 * abs(pdi - mdi) / max(pdi + mdi, 1e-12))
    return mean(dx[-period:]) if dx else 0.0


def _validate(candles: list[dict[str, Any]]) -> list[dict[str, float]]:
    if len(candles) < 30:
        raise ValueError("At least 30 completed candles are required for advanced analysis")
    clean = []
    for i, c in enumerate(candles):
        try:
            row = {k: float(c[k]) for k in ("open", "high", "low", "close")}
            row["volume"] = max(0.0, float(c.get("volume", 0) or 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Each candle needs numeric open, high, low and close values") from exc
        if any(v <= 0 for k, v in row.items() if k != "volume"):
            raise ValueError("OHLC prices must be positive")
        if row["high"] < max(row["open"], row["close"], row["low"]):
            raise ValueError("Candle high is inconsistent with OHLC values")
        if row["low"] > min(row["open"], row["close"], row["high"]):
            raise ValueError("Candle low is inconsistent with OHLC values")
        clean.append(row)
    return clean


def analyze_market(
    candles: list[dict[str, Any]],
    timeframe: str,
    higher_timeframes: dict[str, list[dict[str, Any]]] | None = None,
    asset: str | None = None,
) -> dict[str, Any]:
    """Analyze one asset; optional higher-timeframe candles add trend confirmation."""
    bars = _validate(candles)
    closes = [c["close"] for c in bars]
    last, prev = bars[-1], bars[-2]
    e9, e21, e50, e200 = (_ema(closes, p) for p in (9, 21, 50, 200))
    fast, mid = e9[-1], e21[-1]
    slow = e50[-1]
    long_trend = e200[-1] if e200 else slow
    rsi = _rsi(closes)
    atr = _atr(bars)
    adx = _adx(bars)
    macd_line = fast - mid
    macd_hist = macd_line - ((_ema(closes, 26)[-1] - _ema(closes, 52)[-1])
                             if len(closes) >= 52 else macd_line)
    recent = closes[-20:]
    basis = mean(recent)
    deviation = pstdev(recent)
    upper, lower = basis + 2 * deviation, basis - 2 * deviation
    bb_position = (last["close"] - lower) / max(upper - lower, 1e-12)
    candle_range = max(last["high"] - last["low"], 1e-12)
    body = (last["close"] - last["open"]) / candle_range
    prior_high = max(c["high"] for c in bars[-21:-1])
    prior_low = min(c["low"] for c in bars[-21:-1])
    breakout_up, breakout_down = last["close"] > prior_high, last["close"] < prior_low

    trend_up = fast > mid and mid > slow and last["close"] > long_trend
    trend_down = fast < mid and mid < slow and last["close"] < long_trend
    if adx >= 25 and (trend_up or trend_down):
        regime = "TRENDING"
    elif atr / max(last["close"], 1e-12) > 0.025:
        regime = "HIGH_VOLATILITY"
    else:
        regime = "RANGING_OR_WEAK_TREND"

    score, reasons = 0.0, []
    def add(points: float, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    if trend_up: add(2.0, "EMA 9/21/50 alignment and price above long-term trend")
    elif trend_down: add(-2.0, "EMA 9/21/50 alignment and price below long-term trend")
    if macd_hist > 0: add(1.0, "MACD momentum is positive")
    elif macd_hist < 0: add(-1.0, "MACD momentum is negative")
    if 52 <= rsi <= 68: add(1.0, "RSI confirms bullish momentum")
    elif 32 <= rsi <= 48: add(-1.0, "RSI confirms bearish momentum")
    elif rsi >= 75: add(-0.5, "RSI is stretched; upside entries are penalized")
    elif rsi <= 25: add(0.5, "RSI is stretched; downside entries are penalized")
    if adx >= 25 and trend_up: add(1.0, "ADX confirms a directional bullish trend")
    elif adx >= 25 and trend_down: add(-1.0, "ADX confirms a directional bearish trend")
    if breakout_up: add(1.0, "Close broke above the prior 20-candle high")
    elif breakout_down: add(-1.0, "Close broke below the prior 20-candle low")
    if body >= 0.65: add(0.5, "Strong bullish candle body")
    elif body <= -0.65: add(-0.5, "Strong bearish candle body")
    if bb_position > 1.05: add(0.5, "Price is expanding above the Bollinger envelope")
    elif bb_position < -0.05: add(-0.5, "Price is expanding below the Bollinger envelope")

    mtf = {}
    for tf, tf_candles in (higher_timeframes or {}).items():
        higher = _validate(tf_candles)
        hc = [c["close"] for c in higher]
        if len(hc) < 30:
            continue
        hfast, hslow = _ema(hc, 9)[-1], _ema(hc, 21)[-1]
        bias = "BULLISH" if hfast > hslow else "BEARISH" if hfast < hslow else "NEUTRAL"
        mtf[tf] = bias
        if bias == "BULLISH": add(0.75, f"{tf} higher-timeframe trend is bullish")
        elif bias == "BEARISH": add(-0.75, f"{tf} higher-timeframe trend is bearish")

    direction = "CALL" if score >= 3.5 else "PUT" if score <= -3.5 else "WAIT"
    if direction == "CALL" and rsi >= 75:
        direction = "WAIT"
        reasons.append("Overbought RSI blocks a fresh CALL")
    elif direction == "PUT" and rsi <= 25:
        direction = "WAIT"
        reasons.append("Oversold RSI blocks a fresh PUT")
    max_score = 10.0 + 0.75 * len(mtf)
    confluence = min(100, round(abs(score) / max_score * 100))
    # A conflicting higher timeframe blocks an otherwise directional signal.
    if direction == "CALL" and "BEARISH" in mtf.values():
        direction = "WAIT"
        reasons.append("Conflicting higher-timeframe bias: entry blocked")
    elif direction == "PUT" and "BULLISH" in mtf.values():
        direction = "WAIT"
        reasons.append("Conflicting higher-timeframe bias: entry blocked")
    if regime == "HIGH_VOLATILITY":
        direction = "WAIT"
        reasons.append("Volatility guard: wait for conditions to normalize")

    if atr > 0:
        stop_distance = 1.5 * atr
        target_distance = 2.0 * atr
    else:
        stop_distance = target_distance = None
    trend = ("BULLISH" if trend_up else "BEARISH" if trend_down else
             "NEUTRAL" if pstdev(closes[-20:]) < 1e-12 else "MIXED")
    return {
        "asset": asset,
        "direction": direction,
        "trend": trend,
        "market_regime": regime,
        "signal_strength": "moderate" if direction != "WAIT" else "low",
        "confluence_score": confluence,
        "confidence_is_probability": False,
        "score": round(score, 3),
        "rsi_14": round(rsi, 2),
        "adx_14": round(adx, 2),
        "atr_14": round(atr, 8),
        "ema_9": round(fast, 8),
        "ema_21": round(mid, 8),
        "ema_50": round(slow, 8),
        "ema_200": round(long_trend, 8),
        "macd_histogram_proxy": round(macd_hist, 8),
        "bollinger_position": round(bb_position, 4),
        "breakout": "UP" if breakout_up else "DOWN" if breakout_down else "NONE",
        "higher_timeframe_bias": mtf,
        "last_close": closes[-1],
        "timeframe": timeframe,
        "candle_count": len(bars),
        "suggested_expiry_minutes": {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}.get(timeframe),
        "atr_risk_reference": {"stop_distance": round(stop_distance, 8), "target_distance": round(target_distance, 8)} if stop_distance is not None else None,
        "reasons": reasons,
        "execution_enabled": False,
        "disclaimer": "Research confluence only, not a calibrated win probability or guarantee. Verify completed candles and broker prices; validate per asset/timeframe with walk-forward tests before use.",
    }
