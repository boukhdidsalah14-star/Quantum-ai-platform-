"""Public signal API backed by the advanced multi-factor analysis engine."""
from __future__ import annotations

from typing import Any

from app.advanced_signals import analyze_market


def analyze_candles(
    candles: list[dict[str, Any]],
    timeframe: str,
    higher_timeframes: dict[str, list[dict[str, Any]]] | None = None,
    asset: str | None = None,
) -> dict[str, Any]:
    """Analyze completed OHLC candles; keep the existing app call signature."""
    return analyze_market(
        candles=candles,
        timeframe=timeframe,
        higher_timeframes=higher_timeframes,
        asset=asset,
    )
