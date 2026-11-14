"""Simple no-lookahead directional backtest for the indicator signal engine."""
from __future__ import annotations

from typing import Any

from app.signals import analyze_candles


def backtest_candles(
    candles: list[dict[str, Any]],
    timeframe: str,
    lookahead_candles: int = 1,
) -> dict[str, Any]:
    if not 1 <= int(lookahead_candles) <= 4:
        raise ValueError("Lookahead must be between 1 and 4 candles")
    if len(candles) < 40:
        raise ValueError("At least 40 candles are required for a meaningful backtest")
    wins = losses = ties = skipped = 0
    examples = []
    final_index = len(candles) - lookahead_candles
    for index in range(59, final_index):
        history = candles[: index + 1]
        signal = analyze_candles(history, timeframe)
        direction = signal["direction"]
        if direction == "WAIT":
            skipped += 1
            continue
        entry = float(candles[index]["close"])
        exit_price = float(candles[index + lookahead_candles]["close"])
        if exit_price == entry:
            ties += 1
            outcome = "tie"
        elif (direction == "CALL" and exit_price > entry) or (direction == "PUT" and exit_price < entry):
            wins += 1
            outcome = "win"
        else:
            losses += 1
            outcome = "loss"
        if len(examples) < 8:
            examples.append({
                "candle_index": index,
                "direction": direction,
                "outcome": outcome,
                "entry": entry,
                "exit": exit_price,
            })
    decided = wins + losses
    return {
        "timeframe": timeframe,
        "lookahead_candles": lookahead_candles,
        "candles_tested": len(candles),
        "signals_tested": decided + ties,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "waits": skipped,
        "directional_accuracy_percent": round((wins / decided) * 100, 2) if decided else None,
        "signal_coverage_percent": round(((decided + ties) / max(1, final_index - 59)) * 100, 2),
        "examples": examples,
        "execution_enabled": False,
        "disclaimer": "Historical directional test only. No broker trades, stake, payout, spread, slippage, or future performance is represented.",
    }
