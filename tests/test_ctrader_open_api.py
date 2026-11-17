import asyncio
import json
import time

import pytest
from cryptography.fernet import Fernet

from app.auth import create_customer, init_auth_db
from app import ctrader_open_api as api


class FakeWebSocket:
    def __init__(self, accounts=None):
        self.accounts = accounts or [{
            "ctidTraderAccountId": "123456",
            "traderLogin": "98765",
            "brokerTitleShort": "IC Markets",
            "isLive": False,
        }]
        self.closed = False

    async def send(self, raw):
        message = json.loads(raw)
        kind = message["payloadType"]
        if kind == api.APP_AUTH_REQ:
            response_type, payload = api.APP_AUTH_RES, {}
        elif kind == api.GET_ACCOUNTS_REQ:
            response_type, payload = api.GET_ACCOUNTS_RES, {
                "permissionScope": 1,
                "ctidTraderAccount": self.accounts,
            }
        elif kind == api.ACCOUNT_AUTH_REQ:
            response_type, payload = api.ACCOUNT_AUTH_RES, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
            }
        elif kind == api.TRADER_REQ:
            response_type, payload = api.TRADER_RES, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "trader": {
                    "balance": 12345,
                    "moneyDigits": 2,
                    "depositAssetId": 1,
                    "leverageInCents": 10000,
                },
            }
        elif kind == api.RECONCILE_REQ:
            response_type, payload = api.RECONCILE_RES, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "position": [{
                    "positionId": "77",
                    "tradeData": {"symbolId": "1", "volume": 1000, "tradeSide": 1},
                    "stopLoss": 1.08,
                    "takeProfit": 1.12,
                }],
                "order": [],
            }
        elif kind == api.SYMBOLS_LIST_REQ:
            response_type, payload = api.SYMBOLS_LIST_RES, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "symbol": [
                    {"symbolId": "10", "symbolName": "EUR/USD", "enabled": True},
                    {"symbolId": "11", "symbolName": "XAU/USD", "enabled": True},
                    {"symbolId": "12", "symbolName": "OLD/USD", "enabled": False},
                ],
            }
        elif kind == api.GET_TRENDBARS_REQ:
            response_type, payload = api.GET_TRENDBARS_RES, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "symbolId": message["payload"]["symbolId"],
                "period": message["payload"]["period"],
                "trendbar": [{
                    "low": 107000,
                    "deltaOpen": 100,
                    "deltaHigh": 500,
                    "deltaClose": 200,
                    "utcTimestampInMinutes": int(time.time() // 60) - 5,
                    "volume": 123,
                }],
            }
        else:
            raise AssertionError("Unexpected cTrader request type: " + str(kind))
        self._reply = json.dumps({
            "clientMsgId": message["clientMsgId"],
            "payloadType": response_type,
            "payload": payload,
        })

    async def recv(self):
        return self._reply

    async def close(self):
        self.closed = True


def setup(monkeypatch, tmp_path, accounts=None):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "ctrader-sync.sqlite3"))
    monkeypatch.setenv("QUANTUM_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CTRADER_CLIENT_ID", "client-id")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "client-secret")
    init_auth_db()
    api.init_db()
    customer = create_customer("sync@example.com", "strong-password")
    async def fake_refresh(_customer_id):
        return {"access_token": "test-access-token", "refresh_token": "test-refresh"}
    monkeypatch.setattr(api, "refresh_access_token", fake_refresh)
    fake = FakeWebSocket(accounts)
    async def fake_connect(*args, **kwargs):
        assert args[0] == api.DEMO_WS_URL
        return fake
    monkeypatch.setattr(api.websockets, "connect", fake_connect)
    return customer, fake


def test_discovery_only_returns_ic_markets_demo_accounts(monkeypatch, tmp_path):
    accounts = [
        {"ctidTraderAccountId": "1", "traderLogin": "11", "brokerTitleShort": "IC Markets SC", "isLive": False},
        {"ctidTraderAccountId": "2", "traderLogin": "22", "brokerTitleShort": "Other Broker", "isLive": False},
        {"ctidTraderAccountId": "3", "traderLogin": "33", "brokerTitleShort": "IC Markets", "isLive": True},
    ]
    customer, _ = setup(monkeypatch, tmp_path, accounts)
    result = asyncio.run(api.discover_demo_accounts(customer["id"]))
    assert result == [{
        "account_id": "1",
        "trader_login": "11",
        "broker": "IC Markets SC",
        "is_live": False,
        "environment": "demo",
    }]


def test_sync_demo_account_returns_real_read_only_snapshot(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    result = asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    assert result["connected"] is True
    assert result["environment"] == "demo"
    assert result["balance"] == 123.45
    assert result["trading_enabled"] is False
    assert result["open_positions"][0]["position_id"] == "77"
    assert result["open_positions"][0]["volume_units"] == 10.0
    saved = api.saved_snapshot(customer["id"])
    assert saved["account_id"] == "123456"
    assert saved["balance"] == 123.45


def test_sync_rejects_live_account_even_if_it_appears_in_response(monkeypatch, tmp_path):
    accounts = [{
        "ctidTraderAccountId": "987",
        "traderLogin": "987",
        "brokerTitleShort": "IC Markets",
        "isLive": True,
    }]
    customer, _ = setup(monkeypatch, tmp_path, accounts)
    with pytest.raises(api.CTraderOpenAPIError, match="Live accounts are locked"):
        asyncio.run(api.sync_demo_account(customer["id"], "987"))


def test_sync_rejects_other_broker_and_invalid_account_id(monkeypatch, tmp_path):
    accounts = [{
        "ctidTraderAccountId": "987",
        "traderLogin": "987",
        "brokerTitleShort": "Other Broker",
        "isLive": False,
    }]
    customer, _ = setup(monkeypatch, tmp_path, accounts)
    with pytest.raises(api.CTraderOpenAPIError, match="not identified as IC Markets"):
        asyncio.run(api.sync_demo_account(customer["id"], "987"))
    with pytest.raises(ValueError, match="valid cTrader account"):
        asyncio.run(api.sync_demo_account(customer["id"], "not-an-id"))


def test_account_discovery_requires_trade_permission(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    async def fake_connect(*args, **kwargs):
        class ReadOnlyWS(FakeWebSocket):
            async def send(self, raw):
                message = json.loads(raw)
                if message["payloadType"] == api.APP_AUTH_REQ:
                    payload = {}
                    kind = api.APP_AUTH_RES
                else:
                    payload = {"permissionScope": 0, "ctidTraderAccount": []}
                    kind = api.GET_ACCOUNTS_RES
                self._reply = json.dumps({
                    "clientMsgId": message["clientMsgId"],
                    "payloadType": kind,
                    "payload": payload,
                })
        return ReadOnlyWS()
    monkeypatch.setattr(api.websockets, "connect", fake_connect)
    with pytest.raises(api.CTraderOpenAPIError, match="trading permission"):
        asyncio.run(api.discover_demo_accounts(customer["id"]))


def test_demo_symbol_discovery_returns_enabled_broker_symbols(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    symbols = asyncio.run(api.discover_demo_symbols(customer["id"]))
    assert [item["symbol"] for item in symbols] == ["EUR/USD", "XAU/USD"]
    assert all(item["enabled"] for item in symbols)


def test_demo_candles_transform_ctrader_relative_ohlc(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    result = asyncio.run(api.get_demo_candles(customer["id"], "EURUSD", "15m", 80))
    assert result["symbol"] == "EUR/USD"
    assert result["source"] == "IC Markets cTrader demo market data"
    assert result["execution_enabled"] is False
    candle = result["candles"][0]
    assert candle["low"] == 1.07
    assert candle["open"] == 1.071
    assert candle["high"] == 1.075
    assert candle["close"] == 1.072
    assert candle["volume"] == 123


def test_demo_candles_reject_unknown_symbol_and_timeframe(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    with pytest.raises(ValueError, match="not available"):
        asyncio.run(api.get_demo_candles(customer["id"], "NOTREAL", "15m", 80))
    with pytest.raises(ValueError, match="timeframe"):
        asyncio.run(api.get_demo_candles(customer["id"], "EURUSD", "2h", 80))


def test_normalize_deriv_forex_symbols_for_ctrader():
    assert api._normalize_symbol("frxEURUSD") == "EURUSD"
    assert api._normalize_symbol("frxXAUUSD") == "XAUUSD"
    assert api._normalize_symbol("EUR/USD") == "EURUSD"



def test_ctrader_environment_routes_to_official_gateways():
    assert api._ctrader_ws_url("demo") == "wss://demo.ctraderapi.com:5036"
    assert api._ctrader_ws_url("live") == "wss://live.ctraderapi.com:5036"
    with pytest.raises(ValueError, match="environment"):
        api._ctrader_ws_url("paper")


def test_live_ctrader_session_is_locked_by_default(monkeypatch):
    monkeypatch.delenv("QUANTUM_CTRADER_LIVE_SESSION_ENABLED", raising=False)
    with pytest.raises(api.CTraderOpenAPIError, match="Live cTrader sessions are locked"):
        asyncio.run(api._open_ctrader_session("access-token", "live"))
