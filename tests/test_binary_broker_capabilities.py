from app.brokers import broker_capabilities


def test_only_the_four_selected_platforms_are_listed():
    result = broker_capabilities()
    brokers = {broker["id"]: broker for broker in result["brokers"]}
    assert set(brokers) == {"iq_option", "ic_markets"}
    assert result["execution_enabled"] is False
    assert result["account_mode"] == "demo_first"
    assert all(not broker["connection_verified"] for broker in brokers.values())
    assert all(not broker["execution_enabled"] for broker in brokers.values())
    assert all(not broker["real_execution_enabled"] for broker in brokers.values())
