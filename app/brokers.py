"""Honest broker capability registry; availability is not a live connection."""
from __future__ import annotations

import os


def broker_capabilities() -> dict:
    deriv_configured = all(os.getenv(name, "").strip() for name in (
        "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID", "DERIV_DEMO_TOKEN"
    ))
    persistent_storage_ready = (
        os.getenv("QUANTUM_PERSISTENT_STORAGE", "").strip().lower() == "true"
        and bool(os.getenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", "").strip())
    )
    demo_execution_enabled = (
        persistent_storage_ready
        and os.getenv("QUANTUM_DERIV_DEMO_TRADING_ENABLED", "").strip().lower() == "true"
    )
    return {
        "brokers": [
            {
                "id": "deriv",
                "name": "Deriv",
                "status": "public_market_data_available",
                "demo_status_configured": deriv_configured,
                "connection_verified": False,
                "supported_scope": ["public_forex_market_data", "public_synthetic_market_data",
                                    "forex_binary_signals", "synthetic_binary_signals",
                                    "binary_contract_quote_preview", "demo_account_status", "balance_read"],
                "execution_enabled": False,
                "demo_execution_code_available": True,
                "demo_execution_enabled": demo_execution_enabled,
                "note": ("Deriv VRTC demo binary execution is enabled behind customer verification and risk controls." if demo_execution_enabled else "Public Forex and synthetic market data, signals, and binary quote previews are available. The demo execution engine is implemented but locked until persistent encrypted storage and the explicit demo switch are enabled. Real trading is disabled."),
            },
            {
                "id": "iq_option",
                "name": "IQ Option",
                "status": "compatibility_review",
                "connection_verified": False,
                "supported_scope": [],
                "execution_enabled": False,
                "note": "No official public retail trading API has been verified. Unofficial reverse-engineered clients are not enabled.",
            },
            {
                "id": "mexc",
                "name": "MEXC",
                "status": "public_market_data_connected",
                "connection_verified": False,
                "supported_scope": ["public_spot_market_data", "public_candles"],
                "execution_enabled": False,
                "note": "Public MEXC Spot quotes and candles are connected read-only. Customer account authentication and order execution remain disabled; MEXC has no sandbox.",
            },
        ],
        "execution_enabled": False,
        "account_mode": "demo_first",
    }
