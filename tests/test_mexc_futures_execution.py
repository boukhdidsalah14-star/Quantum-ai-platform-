import hashlib
import hmac
import pytest

from app.mexc_futures_execution import (
    MexcFuturesError, _headers, _parse_assets, _signature,
)


def test_mexc_futures_signature_matches_documented_hmac_target():
    signature = _signature("access", "secret", "1700000000000", "")
    expected = hmac.new(b"secret", b"access1700000000000", hashlib.sha256).hexdigest()
    assert signature == expected


def test_mexc_futures_headers_use_openapi_auth_names():
    headers = _headers("access", "secret", "1700000000000")
    assert headers["ApiKey"] == "access"
    assert headers["Request-Time"] == "1700000000000"
    assert len(headers["Signature"]) == 64
    assert headers["Content-Type"] == "application/json"


def test_mexc_futures_assets_are_normalized_without_secrets():
    result = _parse_assets({"success": True, "code": 0, "data": [{
        "currency": "USDT", "availableBalance": 120, "equity": 125,
        "positionMargin": 5, "unrealized": 3,
    }]})
    assert result["market"] == "usdt_margined_perpetual_futures"
    assert result["assets"][0]["currency"] == "USDT"
    assert result["assets"][0]["available_balance"] == "120"
    assert "api_secret" not in str(result)


def test_mexc_futures_rejects_failed_or_malformed_payloads():
    with pytest.raises(MexcFuturesError):
        _parse_assets({"success": False, "code": 401, "data": []})
    with pytest.raises(MexcFuturesError):
        _parse_assets({"success": True, "code": 0, "data": {}})
