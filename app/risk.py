"""Central demo-only trading risk policy. Real trading is always disabled."""
from __future__ import annotations

import math
from typing import Any

DEFAULT_DEMO_STAKE_USD = 1.0
MIN_DEMO_STAKE_USD = 0.35
MAX_DEMO_STAKE_USD = 2.0
DAILY_LOSS_LIMIT_USD = 25.0
MAX_CONSECUTIVE_LOSSES = 3
MAX_OPEN_DEMO_CONTRACTS = 1
ALLOWED_BINARY_DURATIONS_MINUTES = (1, 5, 10, 15, 30, 60)
REAL_TRADING_ENABLED = False


def validate_demo_quote(stake: float, duration_minutes: int) -> tuple[float, int]:
    try:
        stake_value = float(stake)
        duration_value = int(duration_minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid demo stake or duration") from exc
    if not math.isfinite(stake_value) or not MIN_DEMO_STAKE_USD <= stake_value <= MAX_DEMO_STAKE_USD:
        raise ValueError(f"Demo stake must be between {MIN_DEMO_STAKE_USD:.2f} and {MAX_DEMO_STAKE_USD:.2f} USD")
    if duration_value not in ALLOWED_BINARY_DURATIONS_MINUTES:
        raise ValueError("Duration must be 1, 5, 10, 15, 30, or 60 minutes")
    return round(stake_value, 2), duration_value


def evaluate_demo_risk(
    daily_loss: float,
    consecutive_losses: int,
    open_contracts: int,
) -> dict[str, Any]:
    reasons = []
    if float(daily_loss) >= DAILY_LOSS_LIMIT_USD:
        reasons.append("Daily loss limit reached")
    if int(consecutive_losses) >= MAX_CONSECUTIVE_LOSSES:
        reasons.append("Maximum consecutive losses reached")
    if int(open_contracts) >= MAX_OPEN_DEMO_CONTRACTS:
        reasons.append("An open demo contract is already active")
    return {
        "trading_paused": bool(reasons),
        "pause_reasons": reasons,
        "daily_loss_limit_usd": DAILY_LOSS_LIMIT_USD,
        "max_consecutive_losses": MAX_CONSECUTIVE_LOSSES,
        "max_open_demo_contracts": MAX_OPEN_DEMO_CONTRACTS,
        "default_stake_usd": DEFAULT_DEMO_STAKE_USD,
        "max_stake_usd": MAX_DEMO_STAKE_USD,
        "allowed_durations_minutes": list(ALLOWED_BINARY_DURATIONS_MINUTES),
        "real_trading_enabled": REAL_TRADING_ENABLED,
    }
