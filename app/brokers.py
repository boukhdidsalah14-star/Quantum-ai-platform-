"""Only the platform providers selected for the QUANTUM AI product."""
from __future__ import annotations


def broker_capabilities() -> dict:
    brokers = [
        {
            "id": "iq_option", "name": "IQ Option", "category": "binary_options",
            "status": "signals_only_not_connected", "connection_verified": False,
            "supported_scope": ["public_forex_market_data", "binary_signal_analysis"],
            "execution_enabled": False, "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "IQ Option is listed as a target platform. Account authorization and broker order execution are not connected or enabled.",
        },
        {
            "id": "mexc", "name": "MEXC", "category": "crypto_futures",
            "status": "customer_account_connection_foundation", "connection_verified": False,
            "supported_scope": ["public_market_data", "customer_account_verification"],
            "execution_enabled": False, "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "MEXC account connection foundations are present. Live order execution remains disabled pending a complete audited execution and reconciliation workflow.",
        },
        {
            "id": "ctrader", "name": "cTrader", "category": "forex_trading_platform",
            "status": "oauth_and_demo_api_foundation", "connection_verified": False,
            "supported_scope": ["oauth_authorization", "demo_account_discovery", "demo_position_sync"],
            "execution_enabled": False, "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "cTrader authorization and demo API foundations are present. Customer authorization and live trading are not yet verified.",
        },
        {
            "id": "ic_markets", "name": "IC Markets", "category": "forex_broker",
            "status": "ctrader_broker_target", "connection_verified": False,
            "supported_scope": ["ctrader_account_authorization"],
            "execution_enabled": False, "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "IC Markets is the selected Forex broker through cTrader, subject to account-region and broker permissions.",
        },
    ]
    return {
        "brokers": brokers, "execution_enabled": False, "account_mode": "demo_first",
        "binary_execution_note": "IQ Option account connection and binary order execution are not enabled.",
    }
