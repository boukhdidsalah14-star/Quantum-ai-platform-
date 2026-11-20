import re

from app.auth import authenticate_customer, init_auth_db
from app.admin_auth import (
    init_admin_auth_db, send_owner_login_code, verify_owner_login_code,
)
from app.subscriptions import init_db as init_subscription_db, subscription_for_customer


def test_owner_email_code_grants_one_time_lifetime_admin(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "admin.sqlite3"))
    monkeypatch.setenv("QUANTUM_ADMIN_EMAIL", "smartgoomaps@gmail.com")
    monkeypatch.setenv("QUANTUM_ADMIN_OTP_SECRET", "test-only-secret")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("QUANTUM_EMAIL_FROM", "QUANTUM AI <login@example.com>")
    sent = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, headers, json, timeout):
        sent.update(json)
        return FakeResponse()

    monkeypatch.setattr("app.admin_auth.httpx.post", fake_post)
    init_auth_db()
    init_admin_auth_db()
    init_subscription_db()

    send_owner_login_code("SMARTGOOMAPS@gmail.com")
    match = re.search(r"\b(\d{6})\b", sent["text"])
    assert match
    code = match.group(1)

    owner = verify_owner_login_code("smartgoomaps@gmail.com", code)
    assert owner is not None
    assert owner["role"] == "admin"
    assert owner["email"] == "smartgoomaps@gmail.com"
    assert authenticate_customer("smartgoomaps@gmail.com", "any-password") is None

    access = subscription_for_customer(owner["id"])
    assert access["active"] is True
    assert access["lifetime"] is True
    assert access["status"] == "lifetime"

    # A code is single-use.
    assert verify_owner_login_code("smartgoomaps@gmail.com", code) is None


def test_owner_email_code_is_not_sent_without_provider_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "admin-no-mail.sqlite3"))
    monkeypatch.setenv("QUANTUM_ADMIN_EMAIL", "smartgoomaps@gmail.com")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("QUANTUM_EMAIL_FROM", raising=False)
    monkeypatch.delenv("QUANTUM_ADMIN_OTP_SECRET", raising=False)
    init_auth_db()
    init_admin_auth_db()
    try:
        send_owner_login_code("smartgoomaps@gmail.com")
    except RuntimeError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Email delivery must be configured before sending owner codes")
