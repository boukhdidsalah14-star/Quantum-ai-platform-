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
                "note": "Integration is pending verification of supported API access and terms.",
            },
            {
                "id": "mexc",
                "name": "MEXC",
                "status": "integration_pending",
                "connection_verified": False,
                "supported_scope": [],
                "execution_enabled": False,
                "note": "Exchange account integration is not implemented. Current crypto quotes come from Binance public data.",
            },
        ],
        "execution_enabled": False,
        "account_mode": "demo_first",
    }
