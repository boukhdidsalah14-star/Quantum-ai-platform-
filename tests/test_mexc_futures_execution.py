import hashlib,hmac
from decimal import Decimal
import pytest
from app.mexc_futures_execution import MexcFuturesClient,MexcFuturesError,_headers,_parse_assets,_signature,_contract_symbol,_checked_payload,contracts_for_risk

def test_post_signature_uses_exact_json_body():
    body='{"symbol":"BTC_USDT"}'
    assert _signature("access","secret","1700000000000",body)==hmac.new(b"secret",b"access1700000000000"+body.encode(),hashlib.sha256).hexdigest()

def test_headers_use_openapi_names():
    h=_headers("access","secret","1700000000000","body")
    assert h["ApiKey"]=="access" and h["Request-Time"]=="1700000000000" and len(h["Signature"])==64

def test_assets_normalized_without_secrets():
    result=_parse_assets({"success":True,"code":0,"data":[{"currency":"USDT","availableBalance":120,"equity":125,"positionMargin":5,"unrealized":3}]})
    assert result["market"]=="usdt_margined_perpetual_futures" and result["assets"][0]["available_balance"]=="120"
    assert "api_secret" not in str(result)

def test_exchange_error_rejected():
    with pytest.raises(MexcFuturesError): _checked_payload({"success":False,"code":401,"data":[]})

def test_only_approved_contracts():
    assert _contract_symbol("BTCUSDT")=="BTC_USDT"
    with pytest.raises(ValueError): _contract_symbol("USDCUSDT")

def test_contract_volume_uses_contract_size_and_step():
    p=contracts_for_risk(symbol="BTCUSDT",entry_price=100000,stop_loss=99000,account_balance=1000,risk_percent=.5,leverage=2,
       contract={"contractSize":"0.0001","volUnit":"1","minVol":"1","maxVol":"400000"})
    assert Decimal(p["contracts"])==50 and Decimal(p["notional_usdt"])==500 and Decimal(p["estimated_stop_risk_usdt"])==5

@pytest.mark.parametrize("risk",[0,-1,1.01,float("nan"),float("inf")])
def test_invalid_risk_rejected(risk):
    with pytest.raises(ValueError):
        contracts_for_risk(symbol="BTCUSDT",entry_price=100000,stop_loss=99000,account_balance=1000,risk_percent=risk,leverage=2,
          contract={"contractSize":"0.0001","volUnit":"1","minVol":"1","maxVol":"400000"})

def test_missing_credentials_rejected():
    with pytest.raises(ValueError): MexcFuturesClient("","secret")
