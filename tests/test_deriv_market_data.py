import anyio
import json
import pytest

from app import deriv_market_data as deriv


def test_active_symbols_supports_current_new_api_field_names(monkeypatch):
    async def fake_request(payload, expected_type):
        assert payload == {"active_symbols": "brief"}
        assert expected_type == "active_symbols"
        return {"active_symbols": [
            {"underlying_symbol": "frxEURUSD", "underlying_symbol_name": "EUR/USD",
             "market": "forex", "exchange_is_open": 1, "is_trading_suspended": 0},
            {"underlying_symbol": "R_100", "underlying_symbol_name": "Volatility 100 Index",
             "market": "synthetic_index", "submarket": "random_index",
             "exchange_is_open": 1, "is_trading_suspended": 0},
            {"underlying_symbol": "cryBTCUSD", "underlying_symbol_name": "BTC/USD",
             "market": "cryptocurrency", "exchange_is_open": 1, "is_trading_suspended": 0},
        ]}
    monkeypatch.setattr(deriv, "_request", fake_request)
    forex = anyio.run(deriv.get_active_markets, "forex")
    synthetic = anyio.run(deriv.get_active_markets, "synthetic")
    assert [row["symbol"] for row in forex] == ["frxEURUSD"]
    assert [row["symbol"] for row in synthetic] == ["R_100"]
    assert synthetic[0]["name"] == "Volatility 100 Index"


def test_active_symbols_keeps_legacy_field_fallback(monkeypatch):
    async def fake_request(payload, expected_type):
        return {"active_symbols": [
            {"symbol": "frxGBPUSD", "display_name": "GBP/USD",
             "market": "forex", "exchange_is_open": 1, "is_trading_suspended": 0}
        ]}
    monkeypatch.setattr(deriv, "_request", fake_request)
    rows = anyio.run(deriv.get_active_markets, "forex")
    assert rows[0]["symbol"] == "frxGBPUSD"
    assert rows[0]["name"] == "GBP/USD"


def test_contract_quote_payload_uses_new_api_symbol_name(monkeypatch):
    async def fake_active(category):
        return [{"symbol": "R_100", "is_suspended": False}]
    async def fake_contracts(symbol):
        return {"symbol": symbol, "contracts": [{"contract_type": "CALL"}]}
    async def fake_request(payload, expected_type):
        assert payload["underlying_symbol"] == "R_100"
        assert payload["contract_type"] == "CALL"
        assert payload["amount"] == 1.0
        assert payload["duration"] == 10
        assert expected_type == "proposal"
        return {"proposal": {"id": "proposal-123", "ask_price": 1.0,
                             "payout": 1.85, "longcode": "CALL contract"}}
    monkeypatch.setattr(deriv, "get_active_markets", fake_active)
    monkeypatch.setattr(deriv, "get_available_contracts", fake_contracts)
    monkeypatch.setattr(deriv, "_request", fake_request)
    result = anyio.run(deriv.get_contract_proposal, "R_100", "CALL", 1.0, 10, "m", "USD")
    assert result["quote_only"] is True
    assert result["execution_enabled"] is False
    assert result["payout"] == 1.85


@pytest.mark.parametrize("amount", [0, -1, 2.01, float("nan")])
def test_contract_quote_rejects_invalid_stakes(amount):
    with pytest.raises(ValueError):
        anyio.run(deriv.get_contract_proposal, "R_100", "CALL", amount, 5, "m", "USD")


def test_deriv_tick_quotes_reads_batched_public_ticks(monkeypatch):
    async def fake_active(category):
        return [{"symbol": "frxEURUSD", "is_suspended": False},
                {"symbol": "frxGBPUSD", "is_suspended": False}]
    class FakeSocket:
        def __init__(self):
            self.messages = [
                {"msg_type": "tick", "tick": {"symbol": "frxEURUSD", "quote": 1.12}},
                {"msg_type": "tick", "tick": {"symbol": "frxGBPUSD", "quote": 1.27}},
            ]
        async def send(self, payload):
            assert json.loads(payload)["ticks"] == ["frxEURUSD", "frxGBPUSD"]
        async def recv(self):
            return json.dumps(self.messages.pop(0))
    class FakeConnection:
        def __init__(self):
            self.socket = FakeSocket()
        async def __aenter__(self):
            return self.socket
        async def __aexit__(self, *args):
            return False
    monkeypatch.setattr(deriv, "get_active_markets", fake_active)
    monkeypatch.setattr(deriv.websockets, "connect", lambda **kwargs: FakeConnection())
    quotes = anyio.run(deriv.get_tick_quotes, ["frxEURUSD", "frxGBPUSD"])
    assert quotes == {"frxEURUSD": 1.12, "frxGBPUSD": 1.27}
