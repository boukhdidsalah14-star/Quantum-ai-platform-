import asyncio
import json
import time

import pytest
from cryptography.fernet import Fernet

from app.auth import create_customer, init_auth_db
from app import ctrader_open_api as api
from app.ctrader_permissions import set_demo_permission, CTraderPermissionError


class FakeWebSocket:
    def __init__(self, accounts=None):
        self.accounts = accounts or [{
            "ctidTraderAccountId": "123456",
            "traderLogin": "98765",
            "brokerTitleShort": "IC Markets",
            "isLive": False,
        }]
        self.closed = False
        self.last_order_payload = None
        self.positions = [{
            "positionId": "77",
            "tradeData": {"symbolId": "1", "volume": 1000, "tradeSide": 1},
            "stopLoss": 1.08,
            "takeProfit": 1.12,
        }]

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
                    "accessRights": 0,
                },
            }
        elif kind == api.NEW_ORDER_REQ:
            response_type, payload = api.EXECUTION_EVENT, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "executionType": 3,
                "position": {"positionId": "78"},
                "order": {"orderId": "88"},
            }
        elif kind == api.AMEND_POSITION_SLTP_REQ:
            response_type, payload = api.EXECUTION_EVENT, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "executionType": 2,
                "position": {"positionId": message["payload"]["positionId"]},
            }
        elif kind == api.CLOSE_POSITION_REQ:
            response_type, payload = api.EXECUTION_EVENT, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "executionType": 3,
                "position": {"positionId": message["payload"]["positionId"]},
            }
        elif kind == api.RECONCILE_REQ:
            response_type, payload = api.RECONCILE_RES, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "position": self.positions,
                "order": [],
            }
        elif kind == api.SYMBOLS_LIST_REQ:
            response_type, payload = api.SYMBOLS_LIST_RES, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "symbol": [
                    {"symbolId": "10", "symbolName": "EUR/USD", "enabled": True},
                    {"symbolId": "11", "symbolName": "XAU/USD", "enabled": True},
                    {"symbolId": "13", "symbolName": "BTC/USD", "enabled": True},
                    {"symbolId": "12", "symbolName": "OLD/USD", "enabled": False},
                ],
            }
        elif kind == api.SYMBOL_BY_ID_REQ:
            specs = {
                "10": {"symbolId": "10", "digits": 5, "lotSize": 10000000,
                       "minVolume": 1000, "maxVolume": 100000000, "stepVolume": 1000},
                "11": {"symbolId": "11", "digits": 2, "lotSize": 100,
                       "minVolume": 1, "maxVolume": 100000, "stepVolume": 1},
                "13": {"symbolId": "13", "digits": 2, "lotSize": 100000,
                       "minVolume": 100, "maxVolume": 1000000, "stepVolume": 100},
            }
            response_type, payload = api.SYMBOL_BY_ID_RES, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "symbol": [specs[sid] for sid in message["payload"]["symbolId"] if sid in specs],
            }
        elif kind == api.DEAL_LIST_REQ:
            now_ms = int(time.time() * 1000)
            response_type, payload = api.DEAL_LIST_RES, {
                "ctidTraderAccountId": message["payload"]["ctidTraderAccountId"],
                "deal": [{
                    "dealId": "501", "orderId": "502", "positionId": "77",
                    "symbolId": "10", "volume": 100000, "filledVolume": 100000,
                    "executionPrice": 1.0875, "tradeSide": 1, "dealStatus": 2,
                    "createTimestamp": now_ms - 1000, "executionTimestamp": now_ms,
                    "commission": 250, "moneyDigits": 2, "label": "QUANTUM_AI_DEMO",
                }],
                "hasMore": False,
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
        if kind == api.NEW_ORDER_REQ:
            self.last_order_payload = dict(message["payload"])
            self.positions.append({
                "positionId": "78",
                "tradeData": {"symbolId": "10", "volume": message["payload"]["volume"], "tradeSide": message["payload"]["tradeSide"]},
                "stopLoss": message["payload"].get("stopLoss"),
                "takeProfit": message["payload"].get("takeProfit"),
            })
        elif kind == api.AMEND_POSITION_SLTP_REQ:
            for position in self.positions:
                if str(position["positionId"]) == str(message["payload"]["positionId"]):
                    position["stopLoss"] = message["payload"]["stopLoss"]
                    position["takeProfit"] = message["payload"]["takeProfit"]
        elif kind == api.CLOSE_POSITION_REQ:
            self.positions = [position for position in self.positions
                              if str(position["positionId"]) != str(message["payload"]["positionId"])]
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


def test_account_discovery_does_not_expect_permission_scope_in_accounts_payload(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    result = asyncio.run(api.discover_demo_accounts(customer["id"]))
    assert result[0]["account_id"] == "123456"

def test_demo_symbol_discovery_returns_enabled_broker_symbols(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    symbols = asyncio.run(api.discover_demo_symbols(customer["id"]))
    assert [item["symbol"] for item in symbols] == ["BTC/USD", "EUR/USD", "XAU/USD"]
    assert all(item["enabled"] for item in symbols)
    assert next(item for item in symbols if item["symbol"] == "BTC/USD")["asset_class"] == "crypto"
    assert next(item for item in symbols if item["symbol"] == "EUR/USD")["asset_class"] == "forex"
    assert next(item for item in symbols if item["symbol"] == "BTC/USD")["lot_size"] == 100000


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


def test_ctrader_asset_classifies_crypto_and_forex_symbols():
    assert api.ctrader_symbol_asset_class("BTC/USD") == "crypto"
    assert api.ctrader_symbol_asset_class("ETHUSDT") == "crypto"
    assert api.ctrader_symbol_asset_class("EUR/USD") == "forex"
    assert api.ctrader_symbol_asset_class("XAU/USD") == "metals"



def test_ctrader_environment_routes_to_official_gateways():
    assert api._ctrader_ws_url("demo") == "wss://demo.ctraderapi.com:5036"
    assert api._ctrader_ws_url("live") == "wss://live.ctraderapi.com:5036"
    with pytest.raises(ValueError, match="environment"):
        api._ctrader_ws_url("paper")


def test_live_ctrader_session_is_locked_by_default(monkeypatch):
    monkeypatch.delenv("QUANTUM_CTRADER_LIVE_SESSION_ENABLED", raising=False)
    with pytest.raises(api.CTraderOpenAPIError, match="Live cTrader sessions are locked"):
        asyncio.run(api._open_ctrader_session("access-token", "live"))


def test_demo_order_is_blocked_without_customer_authorization(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    with pytest.raises(CTraderPermissionError, match="not authorized"):
        asyncio.run(api.open_demo_trade(customer["id"], "EURUSD", "BUY", 0.01, 1.07, 1.12))


def test_demo_order_open_uses_broker_execution_event(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    set_demo_permission(customer["id"], "123456", True, True)
    result = asyncio.run(api.open_demo_trade(customer["id"], "EURUSD", "BUY", 0.01, 1.07, 1.12))
    assert result["broker_confirmed"] is True
    assert result["position_id"] == "78"
    assert result["order_id"] == "88"


def test_crypto_order_uses_broker_lot_size_and_volume_step(monkeypatch, tmp_path):
    customer, fake = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    set_demo_permission(customer["id"], "123456", True, True)
    result = asyncio.run(api.open_demo_trade(
        customer["id"], "BTCUSD", "BUY", 0.001, 65000, 70000
    ))
    assert result["broker_confirmed"] is True
    assert fake.last_order_payload["symbolId"] == 13
    assert fake.last_order_payload["volume"] == 100


def test_demo_order_rejects_oversize_and_invalid_side(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="no more than"):
        asyncio.run(api.open_demo_trade(customer["id"], "EURUSD", "BUY", 0.02, 1.0, 2.0))
    with pytest.raises(ValueError, match="BUY or SELL"):
        asyncio.run(api.open_demo_trade(customer["id"], "EURUSD", "LONG", 0.01, 1.0, 2.0))


def test_demo_order_full_lifecycle_open_monitor_amend_close(monkeypatch, tmp_path):
    customer, fake = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    set_demo_permission(customer["id"], "123456", True, True)

    opened = asyncio.run(api.open_demo_trade(
        customer["id"], "EURUSD", "BUY", 0.01, 1.07, 1.12
    ))
    assert opened["broker_confirmed"] is True
    position_id = opened["position_id"]
    assert position_id == "78"

    monitored = asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    current = next(p for p in monitored["open_positions"] if p["position_id"] == position_id)
    assert current["stop_loss"] == 1.07
    assert current["take_profit"] == 1.12

    amended = asyncio.run(api.amend_demo_position(
        customer["id"], position_id, 1.075, 1.125
    ))
    assert amended["broker_confirmed"] is True
    refreshed = asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    updated = next(p for p in refreshed["open_positions"] if p["position_id"] == position_id)
    assert updated["stop_loss"] == 1.075
    assert updated["take_profit"] == 1.125

    closed = asyncio.run(api.close_demo_position(customer["id"], position_id))
    assert closed["broker_confirmed"] is True
    after_close = asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    assert all(p["position_id"] != position_id for p in after_close["open_positions"])
    assert fake.closed is True


def test_demo_position_protection_and_close_require_existing_position(monkeypatch, tmp_path):
    customer, _ = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    amended = asyncio.run(api.amend_demo_position(customer["id"], "77", 1.06, 1.13))
    assert amended["broker_confirmed"] is True
    closed = asyncio.run(api.close_demo_position(customer["id"], "77"))
    assert closed["broker_confirmed"] is True
    assert closed["position_id"] == "77"
    with pytest.raises(api.CTraderOpenAPIError, match="not open"):
        asyncio.run(api.close_demo_position(customer["id"], "999"))


def test_demo_open_rejects_account_without_full_trade_rights(monkeypatch, tmp_path):
    customer, fake = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    set_demo_permission(customer["id"], "123456", True, True)
    original_send = fake.send
    async def restricted_send(raw):
        message = json.loads(raw)
        if message["payloadType"] == api.TRADER_REQ:
            fake._reply = json.dumps({
                "clientMsgId": message["clientMsgId"],
                "payloadType": api.TRADER_RES,
                "payload": {"trader": {"accessRights": 2}},
            })
            return
        await original_send(raw)
    fake.send = restricted_send
    with pytest.raises(api.CTraderOpenAPIError, match="does not have permission"):
        asyncio.run(api.open_demo_trade(customer["id"], "EURUSD", "BUY", 0.01, 1.07, 1.12))



def test_demo_trade_history_reads_broker_deals(monkeypatch, tmp_path):
    customer, _fake = setup(monkeypatch, tmp_path)
    asyncio.run(api.sync_demo_account(customer["id"], "123456"))
    history = asyncio.run(api.get_demo_trade_history(customer["id"], days=7, limit=100))
    assert history["environment"] == "demo"
    assert history["source"] == "IC Markets cTrader Open API deal history"
    assert len(history["deals"]) == 1
    deal = history["deals"][0]
    assert deal["deal_id"] == "501"
    assert deal["symbol"] == "EUR/USD"
    assert deal["side"] == "BUY"
    assert deal["execution_price"] == 1.0875
    assert deal["commission"] == 2.5
    assert history["has_more"] is False


def test_demo_trade_history_rejects_invalid_range(monkeypatch, tmp_path):
    customer, _fake = setup(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="between 1 and 30 days"):
        asyncio.run(api.get_demo_trade_history(customer["id"], days=31, limit=100))
