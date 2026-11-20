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
            "id": "mexc", "name": "MEXC", "category": "crypto_futures",
            "status": "live_futures_adapter_implemented_locked_pending_validation", "connection_verified": False,
            "supported_scope": ["public_usdm_futures_market_data", "customer_account_verification", "signed_usdm_futures_orders", "exchange_side_stop_loss_take_profit", "customer_scoped_auto_strategy", "per_customer_live_consent", "daily_loss_guard", "emergency_stop"],
            "execution_enabled": False, "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "USD-M futures order and auto-strategy code is implemented with customer-scoped consent, credential-version binding, daily loss limits and emergency stop. Real orders remain locked until live account validation and always-on worker verification are complete."        },
        {
            "id": "ctrader", "name": "cTrader", "category": "forex_trading_platform",
            "status": "demo_auto_and_manual_execution_implemented_live_auto_gated_unverified", "connection_verified": False,
            "supported_scope": [
                "oauth_authorization", "demo_account_discovery", "demo_balance_sync",
                "demo_position_sync", "demo_market_orders", "demo_modify_stop_loss_take_profit",
                "demo_close_positions", "demo_trade_history", "demo_auto_strategy",
                "live_account_discovery", "live_balance_and_positions",
                "live_manual_orders_gated", "live_modify_stop_loss_take_profit_gated",
                "live_close_positions_gated", "live_auto_strategy_gated", "per_account_live_consent",
                "server_side_daily_loss_limit", "emergency_stop",
            ],
            "execution_enabled": False, "demo_execution_enabled": True,
            "real_execution_enabled": False,
            "note": "Demo manual and automated strategy execution are implemented and await a customer-account test. Live account sync, manual orders and automated strategy execution are behind separate platform and per-account consent gates; no live orders have been broker-verified.",
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
