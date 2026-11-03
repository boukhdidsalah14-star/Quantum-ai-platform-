import sqlite3

import pytest

from app import olymp_paper


@pytest.fixture
def paper_db(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTUM_DB_PATH", str(tmp_path / "test.sqlite3"))
    with sqlite3.connect(tmp_path / "test.sqlite3") as db:
        db.execute("CREATE TABLE customers (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO customers (id) VALUES ('customer-1')")
    olymp_paper.init_db()
    olymp_paper.set_account_balance("customer-1", 100)
    return "customer-1"


def test_open_and_settle_olymp_paper_call(paper_db, monkeypatch):
    trade = olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 1, 5, 1.08, "key-1", "manual quote")
    assert trade["status"] == "open"
    assert trade["direction"] == "CALL"
    monkeypatch.setattr(olymp_paper.time, "time", lambda: trade["created_at"] + 5 * 60 + 1)
    settled = olymp_paper.settle_trade(paper_db, trade["id"], 1.081, 0.8)
    assert settled["status"] == "settled"
    assert settled["result"] == "win"
    assert settled["pnl"] == pytest.approx(0.8)


def test_idempotency_does_not_create_duplicate_paper_trade(paper_db):
    first = olymp_paper.open_trade(paper_db, "EURUSD", "PUT", 1, 1, 1.08, "same-key", "manual quote")
    second = olymp_paper.open_trade(paper_db, "EURUSD", "PUT", 1, 1, 1.08, "same-key", "manual quote")
    assert first["id"] == second["id"]
    assert len(olymp_paper.list_trades(paper_db)) == 1


@pytest.mark.parametrize("stake,expiry,direction,price", [
    (0.05, 1, "CALL", 1.08),
    (1, 2, "CALL", 1.08),
    (1, 5, "BUY", 1.08),
    (1, 5, "CALL", 0),
])
def test_invalid_paper_trade_inputs_are_rejected(paper_db, stake, expiry, direction, price):
    with pytest.raises(ValueError):
        olymp_paper.open_trade(paper_db, "EURUSD", direction, stake, expiry, price, "bad-key", "manual quote")


def test_maximum_open_paper_trades_is_enforced(paper_db):
    for i in range(3):
        olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 1, 1, 1.08, f"key-{i}", "manual quote")
    with pytest.raises(ValueError, match="Maximum"):
        olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 1, 1, 1.08, "key-4", "manual quote")


def test_customer_isolation(paper_db):
    olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 1, 1, 1.08, "private-key", "manual quote")
    assert olymp_paper.list_trades("another-customer") == []



def test_customer_can_choose_stake_above_old_two_dollar_cap(paper_db):
    olymp_paper.set_account_balance(paper_db, 500)
    trade = olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 25, 5, 1.08, "custom-stake", "manual quote")
    assert trade["stake"] == 25


def test_daily_loss_limit_is_ten_percent_of_configured_balance(paper_db, monkeypatch):
    olymp_paper.set_account_balance(paper_db, 10)
    trade = olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 1, 1, 1.08, "loss-key", "manual quote")
    monkeypatch.setattr(olymp_paper.time, "time", lambda: trade["created_at"] + 61)
    settled = olymp_paper.settle_trade(paper_db, trade["id"], 1.079, 0.82)
    assert settled["pnl"] == -1
    snapshot = olymp_paper.get_risk_snapshot(paper_db)
    assert snapshot["daily_loss_limit"] == 1
    assert snapshot["daily_loss"] == 1
    assert snapshot["trading_paused"] is True
    with pytest.raises(ValueError, match="10%"):
        olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 0.1, 1, 1.08, "blocked-key", "manual quote")


def test_trade_amount_cannot_exceed_configured_balance(paper_db):
    with pytest.raises(ValueError, match="cannot exceed"):
        olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 101, 1, 1.08, "too-large", "manual quote")


def test_account_balance_is_customer_specific(paper_db):
    snapshot = olymp_paper.get_risk_snapshot("another-customer")
    assert snapshot["configured"] is False


def test_open_stakes_reserve_the_remaining_ten_percent_risk_allowance(paper_db):
    olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 7, 5, 1.08, "risk-seven", "manual quote")
    snapshot = olymp_paper.get_risk_snapshot(paper_db)
    assert snapshot["remaining_loss_allowance"] == 3
    with pytest.raises(ValueError, match="remaining 10%"):
        olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 4, 5, 1.08, "risk-four", "manual quote")