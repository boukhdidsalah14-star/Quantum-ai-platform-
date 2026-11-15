import hashlib
import hmac
import json
import time

from app import subscriptions


def test_ipn_signature_is_verified():
    payload = {"z": 2, "a": {"b": 1, "a": True}}
    secret = "test-ipn-secret"
    canonical = json.dumps(subscriptions.sorted_payload(payload), separators=(",", ":"), ensure_ascii=False)
    signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha512).hexdigest()
    assert subscriptions.verify_ipn_signature(payload, signature, secret)
    assert not subscriptions.verify_ipn_signature(payload, "0" * 128, secret)


def test_finished_payment_activates_once_and_extends_subscription(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "quantum.sqlite3"))
    subscriptions.init_db()
    order_id = subscriptions.create_order("customer-1")
    subscriptions.attach_payment(order_id, {
        "payment_id": "payment-123",
        "pay_address": "TExampleAddress",
        "pay_amount": "20",
        "pay_currency": "usdttrc20",
        "payment_status": "waiting",
    })
    payload = {
        "order_id": order_id,
        "payment_id": "payment-123",
        "payment_status": "finished",
        "price_amount": 20,
        "price_currency": "usd",
        "pay_currency": "usdttrc20",
    }
    result = subscriptions.apply_finished_payment(payload)
    assert result["activated"] is True
    assert result["duplicate"] is False
    assert result["expires_at"] > int(time.time()) + 29 * 86400
    duplicate = subscriptions.apply_finished_payment(payload)
    assert duplicate["duplicate"] is True


def test_non_finished_payment_does_not_activate(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "quantum.sqlite3"))
    subscriptions.init_db()
    order_id = subscriptions.create_order("customer-2")
    subscriptions.attach_payment(order_id, {
        "payment_id": "payment-456",
        "pay_address": "TExampleAddress",
        "pay_amount": "20",
        "pay_currency": "usdttrc20",
        "payment_status": "waiting",
    })
    result = subscriptions.apply_finished_payment({
        "order_id": order_id,
        "payment_id": "payment-456",
        "payment_status": "confirming",
        "price_amount": 20,
        "price_currency": "usd",
        "pay_currency": "usdttrc20",
    })
    assert result["activated"] is False
    assert subscriptions.subscription_for_customer("customer-2")["active"] is False


def test_wrong_network_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "quantum.sqlite3"))
    subscriptions.init_db()
    order_id = subscriptions.create_order("customer-3")
    subscriptions.attach_payment(order_id, {
        "payment_id": "payment-789",
        "pay_address": "TExampleAddress",
        "pay_amount": "20",
        "pay_currency": "usdttrc20",
        "payment_status": "waiting",
    })
    payload = {
        "order_id": order_id,
        "payment_id": "payment-789",
        "payment_status": "finished",
        "price_amount": 20,
        "price_currency": "usd",
        "pay_currency": "usdt",
    }
    import pytest
    with pytest.raises(ValueError):
        subscriptions.apply_finished_payment(payload)


def test_payment_checkout_requires_durable_storage(monkeypatch):
    monkeypatch.setenv("NOWPAYMENTS_API_KEY", "test-api-key")
    monkeypatch.setenv("NOWPAYMENTS_IPN_SECRET", "test-ipn-secret")
    monkeypatch.setenv("QUANTUM_PUBLIC_URL", "https://quantum.example")
    monkeypatch.delenv("QUANTUM_PERSISTENT_STORAGE", raising=False)
    assert subscriptions.payment_configured() is False
    monkeypatch.setenv("QUANTUM_PERSISTENT_STORAGE", "true")
    assert subscriptions.payment_configured() is False
    monkeypatch.setenv("DATABASE_URL", "postgresql://quantum:test@localhost/neondb")
    assert subscriptions.payment_configured() is True


def test_pending_order_is_customer_isolated_and_status_can_be_refreshed(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "quantum.sqlite3"))
    subscriptions.init_db()
    order_id = subscriptions.create_order("customer-a")
    subscriptions.attach_payment(order_id, {
        "payment_id": "payment-a",
        "pay_address": "TExampleAddress",
        "pay_amount": "20",
        "pay_currency": "usdttrc20",
        "payment_status": "waiting",
    })
    assert subscriptions.pending_order_for_customer("customer-a")["order_id"] == order_id
    assert subscriptions.pending_order_for_customer("customer-b") is None
    assert subscriptions.update_payment_status(order_id, "payment-a", "confirming") is True
    assert subscriptions.pending_order_for_customer("customer-a")["payment_status"] == "confirming"
    assert subscriptions.update_payment_status(order_id, "wrong-payment", "finished") is False


def test_expired_ipn_updates_order_without_activating(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "quantum.sqlite3"))
    subscriptions.init_db()
    order_id = subscriptions.create_order("customer-expired")
    subscriptions.attach_payment(order_id, {
        "payment_id": "payment-expired",
        "pay_address": "TExampleAddress",
        "pay_amount": "20",
        "pay_currency": "usdttrc20",
        "payment_status": "waiting",
    })
    result = subscriptions.apply_finished_payment({
        "order_id": order_id,
        "payment_id": "payment-expired",
        "payment_status": "expired",
        "price_amount": 20,
        "price_currency": "usd",
        "pay_currency": "usdttrc20",
    })
    assert result["activated"] is False
    assert subscriptions.pending_order_for_customer("customer-expired") is None
    assert subscriptions.subscription_for_customer("customer-expired")["active"] is False


def test_underpaid_finished_callback_cannot_activate(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "quantum.sqlite3"))
    subscriptions.init_db()
    order_id = subscriptions.create_order("customer-underpaid")
    subscriptions.attach_payment(order_id, {
        "payment_id": "payment-underpaid",
        "pay_address": "TExampleAddress",
        "pay_amount": "20",
        "pay_currency": "usdttrc20",
        "payment_status": "waiting",
    })
    with pytest.raises(ValueError, match="below the checkout amount"):
        subscriptions.apply_finished_payment({
            "order_id": order_id,
            "payment_id": "payment-underpaid",
            "payment_status": "finished",
            "price_amount": 20,
            "price_currency": "usd",
            "pay_currency": "usdttrc20",
            "actually_paid": "19.5",
        })
    assert subscriptions.subscription_for_customer("customer-underpaid")["active"] is False
