"""Multi-factor, conservative candle analysis for research and demo workflows.

This module does not predict outcomes or place orders. Signals are deliberately
selective: conflicting indicators, weak trend, or stretched RSI produce WAIT.
"""
from __future__ import annotations

from math import isfinite, sqrt
from statistics import mean
from typing import Any

EXPIRY_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30,
                  "1h": 60, "4h": 240, "1d": 1440}


def _ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError(f"Not enough candles for EMA {period}")
    alpha = 2.0 / (period + 1)
    result = mean(values[:period])
    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)
    return result


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError("Not enough candles for RSI")
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain, avg_loss = mean(gains[:period]), mean(losses[:period])
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _atr(candles: list[dict[str, Any]], period: int = 14) -> float:
    ranges = []
    for index in range(1, len(candles)):
        row, previous = candles[index], candles[index - 1]
        ranges.append(max(
            float(row["high"]) - float(row["low"]),
            abs(float(row["high"]) - float(previous["close"])),
            abs(float(row["low"]) - float(previous["close"])),
        ))
    if len(ranges) < period:
        raise ValueError("Not enough candles for ATR")
    value = mean(ranges[:period])
    for item in ranges[period:]:
        value = (value * (period - 1) + item) / period
    return value


def _adx(candles: list[dict[str, Any]], period: int = 14) -> float:
    plus_dm, minus_dm, true_ranges = [], [], []
    for index in range(1, len(candles)):
        row, previous = candles[index], candles[index - 1]
        up = float(row["high"]) - float(previous["high"])
        down = float(previous["low"]) - float(row["low"])
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        true_ranges.append(max(
            float(row["high"]) - float(row["low"]),
            abs(float(row["high"]) - float(previous["close"])),
            abs(float(row["low"]) - float(previous["close"])),
        ))
    if len(true_ranges) < period * 2:
        return 0.0
    dx_values = []
    for end in range(period, len(true_ranges) + 1):
        tr = sum(true_ranges[end - period:end])
        if tr <= 0:
            dx_values.append(0.0)
            continue
        plus = 100.0 * sum(plus_dm[end - period:end]) / tr
        minus = 100.0 * sum(minus_dm[end - period:end]) / tr
        denominator = plus + minus
        dx_values.append(100.0 * abs(plus - minus) / denominator if denominator else 0.0)
    return mean(dx_values[-period:]) if dx_values else 0.0


def analyze_candles(candles: list[dict[str, Any]], timeframe: str) -> dict[str, Any]:
    if len(candles) < 50:
        raise ValueError("At least 50 completed candles are required")
    required = ("open", "high", "low", "close")
    normalized = []
    for item in candles:
        row = {key: float(item[key]) for key in required}
        if not all(isfinite(value) and value > 0 for value in row.values()):
            raise ValueError("Candles must contain finite positive OHLC values")
        if row["high"] < max(row["open"], row["close"], row["low"]):
            raise ValueError("Invalid candle high")
        if row["low"] > min(row["open"], row["close"], row["high"]):
            raise ValueError("Invalid candle low")
        if "volume" in item:
            volume = float(item["volume"])
            if not isfinite(volume) or volume < 0:
                raise ValueError("Invalid candle volume")
            row["volume"] = volume
        normalized.append(row)

    closes = [row["close"] for row in normalized]
    fast, slow = _ema(closes, 9), _ema(closes, 21)
    ema_50 = _ema(closes, 50)
    rsi = _rsi(closes)
    atr = _atr(normalized)
    adx = _adx(normalized)
    macd = _ema(closes, 12) - _ema(closes, 26)
    macd_signal = _ema([_ema(closes[:index + 1], 12) - _ema(closes[:index + 1], 26)
                        for index in range(25, len(closes))], 9)
    last, previous = normalized[-1], normalized[-2]
    candle_range = max(last["high"] - last["low"], 1e-12)
    body_ratio = (last["close"] - last["open"]) / candle_range
    recent_mean = mean(closes[-20:])
    deviation = sqrt(mean((value - recent_mean) ** 2 for value in closes[-20:]))
    upper_band, lower_band = recent_mean + 2 * deviation, recent_mean - 2 * deviation

    score, reasons = 0, []
    if fast > slow and closes[-1] > ema_50:
        score += 2
        reasons.append("EMA 9/21 alignment and price above EMA 50 support an uptrend")
    elif fast < slow and closes[-1] < ema_50:
        score -= 2
        reasons.append("EMA 9/21 alignment and price below EMA 50 support a downtrend")
    else:
        reasons.append("Moving averages are mixed; trend confirmation is weak")

    if macd > macd_signal:
        score += 1
        reasons.append("MACD momentum is positive")
    elif macd < macd_signal:
        score -= 1
        reasons.append("MACD momentum is negative")

    if 52 <= rsi <= 68:
        score += 1
        reasons.append("RSI confirms bullish momentum without being stretched")
    elif 32 <= rsi <= 48:
        score -= 1
        reasons.append("RSI confirms bearish momentum without being stretched")
    elif rsi >= 72:
        reasons.append("RSI is overbought; bullish entries are blocked")
    elif rsi <= 28:
        reasons.append("RSI is oversold; bearish entries are blocked")

    if body_ratio >= 0.35:
        score += 1
        reasons.append("Latest candle closed with bullish body strength")
    elif body_ratio <= -0.35:
        score -= 1
        reasons.append("Latest candle closed with bearish body strength")

    if last["close"] > upper_band:
        score = min(score, 0)
        reasons.append("Price is above the upper Bollinger band; breakout needs confirmation")
    elif last["close"] < lower_band:
        score = max(score, 0)
        reasons.append("Price is below the lower Bollinger band; breakdown needs confirmation")

    volume_ratio = None
    if all("volume" in row for row in normalized[-21:]):
        baseline = mean(row["volume"] for row in normalized[-21:-1])
        volume_ratio = round(last["volume"] / baseline, 3) if baseline > 0 else None
        if volume_ratio is not None and volume_ratio < 0.5:
            score = 0
            reasons.append("Current volume is weak versus its 20-candle average")

    if adx < 16:
        score = 0
        reasons.append("ADX indicates a weak or ranging trend; directional entries are filtered")

    if rsi >= 72 and score > 0:
        score = 0
    if rsi <= 28 and score < 0:
        score = 0

    direction = "CALL" if score >= 4 else "PUT" if score <= -4 else "WAIT"
    strength = "high" if abs(score) >= 5 and adx >= 25 else "moderate" if abs(score) == 4 else "low"
    if direction == "WAIT":
        strength = "low"

    close = closes[-1]
    return {
        "direction": direction,
        "trend": "BULLISH" if fast > slow and close > ema_50 else
                 "BEARISH" if fast < slow and close < ema_50 else "NEUTRAL",
        "signal_strength": strength,
        "score": score,
        "rsi_14": round(rsi, 2),
        "ema_9": round(fast, 8),
        "ema_21": round(slow, 8),
        "ema_50": round(ema_50, 8),
        "macd": round(macd, 8),
        "macd_signal": round(macd_signal, 8),
        "adx_14": round(adx, 2),
        "atr_14": round(atr, 8),
        "bollinger_upper": round(upper_band, 8),
        "bollinger_middle": round(recent_mean, 8),
        "bollinger_lower": round(lower_band, 8),
        "volume_ratio_20": volume_ratio,
        "last_close": close,
        "previous_close": previous["close"],
        "timeframe": timeframe,
        "suggested_expiry_minutes": EXPIRY_MINUTES.get(timeframe),
        "reasons": reasons,
        "candle_count": len(normalized),
        "execution_enabled": False,
        "disclaimer": "Multi-indicator research only. No accuracy or profit is guaranteed. Confirm executable broker prices and validate with out-of-sample demo testing.",
    }
