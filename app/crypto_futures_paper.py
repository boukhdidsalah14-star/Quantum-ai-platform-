"""Risk-limited planning for simulated MEXC perpetual-futures trades.

This module only creates paper-trade plans. It never connects to an exchange
account, signs requests, or places orders.
"""
from __future__ import annotations

from math import isfinite

MAX_NOTIONAL_USDT = 500.0
MAX_RISK_PERCENT = 1.0
DEFAULT_RISK_PERCENT = 0.5
DEFAULT_LEVERAGE = 1
MAX_LEVERAGE = 20
STOP_ATR_MULTIPLE = 1.5
TARGET_R_MULTIPLE = 2.0


def build_paper_trade_plan(
    analysis: dict,
    *,
    account_balance: float,
    risk_percent: float = DEFAULT_RISK_PERCENT,
    leverage: int = DEFAULT_LEVERAGE,
) -> dict | None:
    """Return a bounded LONG/SHORT plan, or None when analysis says WAIT."""
    try:
        balance = float(account_balance)
        risk_pct = float(risk_percent)
        price = float(analysis["last_close"])
        atr = float(analysis["atr_14"])
        leverage_numeric = float(leverage)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError("Analysis, balance, ATR, and whole-number leverage are required")

    if not all(isfinite(v) for v in (balance, risk_pct, price, atr, leverage_numeric)):
        raise ValueError("Trade-plan inputs must be finite numbers")
    if isinstance(leverage, bool) or not leverage_numeric.is_integer() or not 1 <= leverage_numeric <= MAX_LEVERAGE:
        raise ValueError("Leverage must be a whole number from 1x to 20x")
    leverage_value = int(leverage_numeric)
    if not all(isfinite(v) for v in (balance, risk_pct, price, atr)):
        raise ValueError("Trade-plan inputs must be finite numbers")
    if balance <= 0 or price <= 0 or atr <= 0:
        raise ValueError("Balance, price, and ATR must be positive")
    if risk_pct <= 0 or risk_pct > MAX_RISK_PERCENT:
        raise ValueError("Paper risk must be greater than 0 and no more than 1%")

    bias = str(analysis.get("trade_bias", "")).upper()
    strength = str(analysis.get("signal_strength", "")).lower()
    if bias == "WAIT":
        return None
    if bias not in {"LONG", "SHORT"}:
        raise ValueError("Trade bias must be LONG, SHORT, or WAIT")
    if strength != "high":
        return None

    stop_distance = atr * STOP_ATR_MULTIPLE
    risk_budget = balance * risk_pct / 100.0
    risk_sized_quantity = risk_budget / stop_distance
    notional_capped_quantity = MAX_NOTIONAL_USDT / price
    quantity = min(risk_sized_quantity, notional_capped_quantity)
    if not isfinite(quantity) or quantity <= 0:
        raise ValueError("Could not calculate a valid paper-trade quantity")

    if bias == "LONG":
        stop_loss = price - stop_distance
        take_profit = price + stop_distance * TARGET_R_MULTIPLE
    else:
        stop_loss = price + stop_distance
        take_profit = price - stop_distance * TARGET_R_MULTIPLE

    notional = quantity * price
    return {
        "mode": "paper",
        "execution": "simulated_only",
        "broker_order_sent": False,
        "side": bias.lower(),
        "entry_price": price,
        "quantity": quantity,
        "notional_usdt": notional,
        "margin_required_usdt": notional / leverage_value,
        "risk_budget_usdt": risk_budget,
        "risk_percent": risk_pct,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward_ratio": TARGET_R_MULTIPLE,
        "max_notional_usdt": MAX_NOTIONAL_USDT,
        "leverage": leverage_value,
    }
