"""Honest broker capability registry; availability is not a live connection.

Binary broker candidates are listed separately from executable integrations.
A website/session automation claim is not treated as an official broker API.
"""
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
    brokers = [
        {
            "id": "deriv",
            "name": "Deriv",
            "category": "binary_options",
            "status": "demo_execution_implemented_locked",
            "demo_status_configured": deriv_configured,
            "connection_verified": False,
            "supported_scope": ["public_forex_market_data", "public_synthetic_market_data",
                                "forex_binary_signals", "synthetic_binary_signals",
                                "binary_contract_quote_preview", "demo_account_status", "balance_read"],
            "execution_enabled": False,
            "demo_execution_code_available": True,
            "demo_execution_enabled": demo_execution_enabled,
            "real_execution_enabled": False,
            "note": ("Deriv VRTC demo binary execution is behind customer verification, durable encrypted storage, and an explicit demo switch."
                     if demo_execution_enabled else "Demo execution code exists but is locked until durable encrypted storage and the explicit demo switch are enabled. Real trading is disabled."),
        },
        {
            "id": "quotex",
            "name": "Quotex",
            "category": "binary_options",
            "status": "not_supported_no_official_api",
            "connection_verified": False,
            "supported_scope": ["signals_only"],
            "execution_enabled": False,
            "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "No official public trading API or broker-issued API credentials were verified. Third-party desktop automation is not a supported customer execution integration. Quotex rules also warn that automated trading software may trigger account closure.",
        },
        {
            "id": "expert_option",
            "name": "ExpertOption",
            "category": "binary_options",
            "status": "candidate_unofficial_interface_only",
            "connection_verified": False,
            "supported_scope": ["candidate_for_demo_connector_review", "signals"],
            "execution_enabled": False,
            "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "Third-party automation claims exist, but official public retail order API access and broker authorization have not been verified. Not connected.",
        },
        {
            "id": "olymp_trade",
            "name": "Olymp Trade",
            "category": "fixed_time_trading",
            "status": "signal_and_paper_foundation",
            "connection_verified": False,
            "supported_scope": ["signal_analysis_from_verified_candles", "paper_execution"],
            "execution_enabled": False,
            "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "Quantum AI can analyze verified candle data and simulate trades. Olymp Trade permits some trading robots under conditions, but no official public third-party order API or broker-issued integration credentials have been verified. Live broker execution is not connected or enabled.",
        },
        {
            "id": "mexc",
            "name": "MEXC",
            "category": "crypto_spot",
            "status": "read_only_customer_account_connection_implemented",
            "connection_verified": False,
            "supported_scope": ["public_spot_market_data", "public_candles",
                                "customer_signed_read_only_account_verification",
                                "encrypted_customer_credential_storage_when_durable_storage_is_ready"],
            "execution_enabled": False,
            "demo_execution_enabled": False,
            "real_execution_enabled": False,
            "note": "Public Spot data and authenticated read-only customer account verification are implemented. Credentials are stored only with durable encrypted storage. No order route is connected; MEXC has no sandbox, so live orders remain locked pending a complete audited execution and reconciliation workflow.",
        },
    ]
    return {
        "brokers": brokers,
        "execution_enabled": False,
        "account_mode": "demo_first",
        "binary_execution_note": "Only a broker with a documented, authorized execution interface can be enabled for customer demo or real orders.",
    }
