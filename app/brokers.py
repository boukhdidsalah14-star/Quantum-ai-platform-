"""Honest broker capability registry; availability is not a live connection."""
from __future__ import annotations

import os


def broker_capabilities() -> dict:
    deriv_configured = all(os.getenv(name, "").strip() for name in (
        "DERIV_APP_ID", "DERIV_DEMO_ACCOUNT_ID", "DERIV_DEMO_TOKEN"
    ))
    return {
        "brokers": [
            {
                "id": "deriv",
                "name": "Deriv",
                "status": "demo_status_configured" if deriv_configured else "demo_status_setup_required",
                "connection_verified": False,
                "supported_scope": ["demo_account_status", "balance_read", "active_symbols_read"],
                "execution_enabled": False,
                "note": "Read-only demo status connector. No orders can be placed.",
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
