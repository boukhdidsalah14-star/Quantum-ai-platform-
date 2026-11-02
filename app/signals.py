"""Transparent, conservative candle-based market signal calculations.

Signals are educational indicators, not predictions or guaranteed trade instructions.
"""
from __future__ import annotations

from statistics import mean
from typing import Any


def _ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError("Not enough candles for EMA")
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
    avg_gain = mean(gains[:period])
    avg_loss = mean(losses[:period])
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def analyze_candles(candles: list[dict[str, Any]], timeframe: str) -> dict[str, Any]:
    if len(candles) < 30:
        raise ValueError("At least 30 completed candles are required")
    closes = [float(item["close"]) for item in candles]
    if any(value <= 0 for value in closes):
        raise ValueError("Invalid candle close price")
    fast = _ema(closes, 9)
    slow = _ema(closes, 21)
    rsi = _rsi(closes, 14)
    last = candles[-1]
    previous = candles[-2]
    candle_range = max(float(last["high"]) - float(last["low"]), 1e-12)
    body_ratio = (float(last["close"]) - float(last["open"])) / candle_range
    trend = "BULLISH" if fast > slow else "BEARISH" if fast < slow else "NEUTRAL"

    score = 0
    reasons = []
    if fast > slow:
        score += 1
        reasons.append("EMA 9 is above EMA 21")
    elif fast < slow:
        score -= 1
        reasons.append("EMA 9 is below EMA 21")
    if closes[-1] > closes[-4]:
        score += 1
        reasons.append("Recent closes show upward momentum")
    elif closes[-1] < closes[-4]:
        score -= 1
        reasons.append("Recent closes show downward momentum")
    if body_ratio > 0.25:
        score += 1
        reasons.append("Latest candle closed with bullish body strength")
    elif body_ratio < -0.25:
        score -= 1
        reasons.append("Latest candle closed with bearish body strength")
    if 50 <= rsi <= 68:
        score += 1
        reasons.append("RSI supports bullish momentum without being overbought")
    elif 32 <= rsi <= 50:
        score -= 1
        reasons.append("RSI supports bearish momentum without being oversold")
    elif rsi > 75:
        reasons.append("RSI is overbought; fresh CALL signals are blocked")
        score = min(score, 0)
    elif rsi < 25:
        reasons.append("RSI is oversold; fresh PUT signals are blocked")
        score = max(score, 0)

    if score >= 3:
        direction = "CALL"
    elif score <= -3:
        direction = "PUT"
    else:
        direction = "WAIT"
    confidence = "moderate" if abs(score) == 3 else "low"
    if direction == "WAIT":
        confidence = "low"

    return {
        "direction": direction,
        "trend": trend,
        "signal_strength": confidence,
        "score": score,
        "rsi_14": round(rsi, 2),
        "ema_9": round(fast, 8),
        "ema_21": round(slow, 8),
        "last_close": closes[-1],
        "timeframe": timeframe,
        "suggested_expiry_minutes": {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}.get(timeframe),
        "reasons": reasons,
        "candle_count": len(candles),
        "execution_enabled": False,
        "disclaimer": "Indicator-based research only. Not a guarantee or financial advice. Confirm with broker prices and test on demo.",
    }
