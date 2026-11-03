"""Offline safety tests for the Deriv demo execution gate and ledger."""
import os
import sqlite3
import tempfile
import unittest

from app.deriv_trading import (
    DerivExecutionError,
    execute_demo_binary_trade,
    init_deriv_trading_db,
    reserve_trade,
    risk_snapshot,
)


class DerivDemoLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ["QUANTUM_DB_PATH"] = os.path.join(self.temp.name, "quantum.sqlite3")
        with sqlite3.connect(os.environ["QUANTUM_DB_PATH"]) as db:
            db.execute("CREATE TABLE customers (id TEXT PRIMARY KEY)")
            db.execute("INSERT INTO customers(id) VALUES ('customer-1')")
        init_deriv_trading_db()

    def tearDown(self):
        self.temp.cleanup()
        os.environ.pop("QUANTUM_DB_PATH", None)

    def test_idempotency_prevents_duplicate_reservation(self):
        first, duplicate_first = reserve_trade(
            "customer-1", "VRTC12345", "frxEURUSD", "CALL", 1.0, 5, "same-key"
        )
        second, duplicate_second = reserve_trade(
            "customer-1", "VRTC12345", "frxEURUSD", "CALL", 1.0, 5, "same-key"
        )
        self.assertFalse(duplicate_first)
        self.assertTrue(duplicate_second)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(risk_snapshot("customer-1")["open_contracts"], 1)

    def test_only_one_open_contract_is_reserved(self):
        reserve_trade("customer-1", "VRTC12345", "frxEURUSD", "CALL", 1.0, 5, "first")
        with self.assertRaisesRegex(ValueError, "open or unconfirmed"):
            reserve_trade("customer-1", "VRTC12345", "frxGBPUSD", "PUT", 1.0, 5, "second")

    def test_real_account_id_is_rejected_before_network_access(self):
        with self.assertRaises(DerivExecutionError):
            import asyncio
            asyncio.run(execute_demo_binary_trade(
                "not-a-token", "CR123456", "12345", "frxEURUSD", "CALL", 1.0, 5
            ))

    def test_invalid_stake_and_duration_are_rejected(self):
        with self.assertRaises(ValueError):
            reserve_trade("customer-1", "VRTC12345", "frxEURUSD", "CALL", 3.0, 5, "large")
        with self.assertRaises(ValueError):
            reserve_trade("customer-1", "VRTC12345", "frxEURUSD", "CALL", 1.0, 2, "duration")


if __name__ == "__main__":
    unittest.main()
