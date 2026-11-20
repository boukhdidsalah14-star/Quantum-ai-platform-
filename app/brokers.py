"""Only the platform providers selected for the QUANTUM AI product."""
from __future__ import annotations


def broker_capabilities() -> dict:
    """Describe implemented capability separately from customer connection state.

    Demo order endpoints exist, but a customer must still authorize their own
    cTrader account, select an IC Markets demo account, and grant explicit
    per-account consent. No live Forex execution is enabled.
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
            "id": "mexc", "name": "MEXC", "category": "crypto_futures",
            "status": "live_futures_adapter_implemented_locked_pending_validation", "connection_verified": False,
            "supported_scope": ["public_usdm_futures_market_data", "customer_account_verification", "signed_usdm_futures_orders", "exchange_side_stop_loss_take_profit", "customer_scoped_auto_strategy", "per_customer_live_consent", "daily_loss_guard", "emergency_stop"],
            "execution_enabled": False, "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "USD-M futures order and auto-strategy code is implemented with customer-scoped consent, credential-version binding, daily loss limits and emergency stop. Real orders remain locked until live account validation and always-on worker verification are complete."        },
        {
            "id": "ctrader", "name": "cTrader", "category": "forex_trading_platform",
            "status": "demo_execution_implemented_customer_verification_required", "connection_verified": False,
            "supported_scope": [
                "oauth_authorization", "demo_account_discovery", "demo_balance_sync",
                "demo_position_sync", "demo_market_orders", "demo_modify_stop_loss_take_profit",
                "demo_close_positions", "demo_trade_history",
            ],
            "execution_enabled": False, "demo_execution_enabled": True,
            "real_execution_enabled": False,
            "note": "Manual demo order, protection-update and close endpoints are implemented. They require the customer's own authorized IC Markets demo account, explicit per-account consent and server-side risk checks. Actual broker execution still needs end-to-end customer-account verification. Live execution is locked.",
        },
        {
            "id": "ic_markets", "name": "IC Markets", "category": "forex_broker",
            "status": "ctrader_demo_execution_implemented_unverified", "connection_verified": False,
            "supported_scope": [
                "ctrader_account_authorization", "demo_balance_and_positions",
                "demo_manual_order_execution", "demo_position_protection", "demo_position_close",
            ],
            "execution_enabled": False, "demo_execution_enabled": True,
            "real_execution_enabled": False,
            "note": "IC Markets is integrated through cTrader. Demo execution is implemented but still requires a real customer-owned demo account test. No live Forex order execution is enabled.",
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
