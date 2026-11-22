"""Only the platform providers selected for the QUANTUM AI product."""
from __future__ import annotations


def broker_capabilities() -> dict:
    """Describe implemented capability separately from customer connection state.

    Demo order endpoints exist. Live-account and order lifecycle code is implemented behind independent Spotware/server approval and customer-consent gates; it has not been validated against a customer live account.
    """
    brokers = [
        {
            "id": "iq_option", "name": "IQ Option", "category": "binary_options",
            "status": "signals_only_not_connected", "connection_verified": False,
            "supported_scope": ["public_forex_market_data", "binary_signal_analysis"],
            "execution_enabled": False, "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "Signals and market analysis only. IQ Option account authorization and order execution are not connected.",
        },
        {
            "id": "ic_markets", "name": "IC Markets", "category": "forex_broker",
            "status": "ctrader_demo_and_gated_live_adapter_unverified", "connection_verified": False,
            "supported_scope": [
                "ctrader_account_authorization", "demo_balance_and_positions",
                "demo_manual_order_execution", "demo_auto_strategy", "demo_position_protection", "demo_position_close",
                "live_account_sync_gated", "live_manual_order_lifecycle_gated", "live_auto_strategy_gated",
            ],
            "execution_enabled": False, "demo_execution_enabled": True,
            "real_execution_enabled": False,
            "note": "IC Markets is integrated through cTrader. Demo manual and automated Forex strategy execution are implemented. Live manual and automated execution are separately gated and require customer-owned account validation and explicit authorization.",
        },
    ]
    return {
        "brokers": brokers,
        "execution_enabled": False,
        "demo_execution_available": True,
        "live_execution_enabled": False,
        "account_mode": "demo_first",
        "binary_execution_note": "IQ Option is signals-only; no binary orders are sent.",
    }
