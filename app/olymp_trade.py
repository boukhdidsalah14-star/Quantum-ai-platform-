"""Olymp Trade signal and paper-trading boundary.

This module deliberately does not authenticate to Olymp Trade or submit broker
orders. It accepts candle data only from a separately verified market-data
source and reuses Quantum AI's transparent indicator analysis.
"""
from __future__ import annotations

from typing import Any

from app.signals import analyze_candles


BROKER_ID = "olymp_trade"
TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}


def analyze_signal(candles: list[dict[str, Any]], timeframe: str) -> dict[str, Any]:
    """Analyze completed candles for an Olymp Trade manual/paper workflow."""
    if timeframe not in TIMEFRAMES:
        raise ValueError("Unsupported Olymp Trade signal timeframe")
    result = analyze_candles(candles, timeframe)
    return {
        **result,
        "broker": BROKER_ID,
        "broker_connection": "not_connected",
        "execution_mode": "signal_only",
        "execution_enabled": False,
        "data_source_requirement": "verified_market_data_required",
        "disclaimer": (
            "Research signal only. Candle prices must be independently verified "
            "against the broker before any manual decision. No Olymp Trade order "
            "is submitted by this module."
        ),
    }


def capabilities() -> dict[str, Any]:
    return {
        "broker": BROKER_ID,
        "status": "signal_and_paper_foundation",
        "market_data_connected": False,
        "account_connected": False,
        "signal_analysis": True,
        "paper_execution": True,
        "demo_order_execution": False,
        "real_order_execution": False,
        "official_order_api_verified": False,
    }
