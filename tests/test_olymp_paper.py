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
    return "customer-1"


def test_open_and_settle_olymp_paper_call(paper_db):
    trade = olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 1, 5, 1.08, "key-1")
    assert trade["status"] == "open"
    assert trade["direction"] == "CALL"
    settled = olymp_paper.settle_trade(paper_db, trade["id"], 1.081, 0.8)
    assert settled["status"] == "settled"
    assert settled["result"] == "win"
    assert settled["pnl"] == pytest.approx(0.8)


def test_idempotency_does_not_create_duplicate_paper_trade(paper_db):
    first = olymp_paper.open_trade(paper_db, "EURUSD", "PUT", 1, 1, 1.08, "same-key")
    second = olymp_paper.open_trade(paper_db, "EURUSD", "PUT", 1, 1, 1.08, "same-key")
    assert first["id"] == second["id"]
    assert len(olymp_paper.list_trades(paper_db)) == 1


@pytest.mark.parametrize("stake,expiry,direction,price", [
    (3, 1, "CALL", 1.08),
    (1, 2, "CALL", 1.08),
    (1, 5, "BUY", 1.08),
    (1, 5, "CALL", 0),
])
def test_invalid_paper_trade_inputs_are_rejected(paper_db, stake, expiry, direction, price):
    with pytest.raises(ValueError):
        olymp_paper.open_trade(paper_db, "EURUSD", direction, stake, expiry, price, "bad-key")


def test_maximum_open_paper_trades_is_enforced(paper_db):
    for i in range(3):
        olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 1, 1, 1.08, f"key-{i}")
    with pytest.raises(ValueError, match="Maximum"):
        olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 1, 1, 1.08, "key-4")


def test_customer_isolation(paper_db):
    olymp_paper.open_trade(paper_db, "EURUSD", "CALL", 1, 1, 1.08, "private-key")
    assert olymp_paper.list_trades("another-customer") == []
