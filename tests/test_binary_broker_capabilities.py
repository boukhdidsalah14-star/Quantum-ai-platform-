import os

from app.brokers import broker_capabilities


def test_non_deriv_binary_candidates_are_never_claimed_as_connected_or_executable(monkeypatch):
    for name in (
        "QUANTUM_PERSISTENT_STORAGE",
        "QUANTUM_CREDENTIALS_ENCRYPTION_KEY",
        "QUANTUM_DERIV_DEMO_TRADING_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    result = broker_capabilities()
    brokers = {broker["id"]: broker for broker in result["brokers"]}

    for broker_id in ("quotex", "expert_option", "olymp_trade"):
        broker = brokers[broker_id]
        assert broker["connection_verified"] is False
        assert broker["execution_enabled"] is False
        assert broker["demo_execution_enabled"] is False
        assert broker["real_execution_enabled"] is False


def test_quotex_is_marked_unsupported_until_official_execution_access_is_verified():
    quotex = next(
        broker for broker in broker_capabilities()["brokers"]
        if broker["id"] == "quotex"
    )
    assert quotex["status"] == "not_supported_no_official_api"
    assert "account closure" in quotex["note"]


def test_global_execution_stays_disabled():
    result = broker_capabilities()
    assert result["execution_enabled"] is False
    assert result["account_mode"] == "demo_first"
