from app.brokers import broker_capabilities


def test_ctrader_registry_reports_read_only_demo_scope(monkeypatch):
    for name in (
        "CTRADER_CLIENT_ID",
        "CTRADER_CLIENT_SECRET",
        "CTRADER_REDIRECT_URI",
        "QUANTUM_CREDENTIALS_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    registry = broker_capabilities()
    ctrader = next(item for item in registry["brokers"] if item["id"] == "icmarkets_ctrader")

    assert ctrader["status"] == "read_only_demo_sync_implemented"
    assert ctrader["connection_verified"] is False
    assert ctrader["production_available"] is True
    assert ctrader["application_configured"] is False
    assert ctrader["demo_execution_code_available"] is False
    assert ctrader["demo_execution_enabled"] is False
    assert ctrader["real_execution_enabled"] is False
    assert "demo_balance_read" in ctrader["supported_scope"]
    assert "demo_open_position_sync" in ctrader["supported_scope"]
    assert "demo_order_placement" not in ctrader["supported_scope"]
    assert registry["execution_enabled"] is False
