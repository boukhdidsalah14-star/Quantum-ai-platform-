import os
import tempfile
import unittest
from pathlib import Path

from app import virtual_platforms as vp


class VirtualPlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["QUANTUM_DB_PATH"] = str(Path(self.tmp.name) / "test.sqlite3")
        with vp.dbopen() as db:
            db.execute("CREATE TABLE customers (id TEXT PRIMARY KEY)")
            db.execute("INSERT INTO customers(id) VALUES('customer-1')")
        vp.init_db()

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_account_starts_at_requested_balance(self):
        accounts = vp.snapshot("customer-1")
        self.assertEqual(accounts["binary"]["balance"], 63578.0)
        self.assertEqual(accounts["forex"]["balance"], 13790.0)
        self.assertEqual(accounts["crypto"]["balance"], 78578.0)

    def test_crypto_virtual_profit_updates_only_crypto_account(self):
        trade = vp.open_position("customer-1", "crypto", "BTCUSDT", "BUY", 100, 100, 5, "crypto-1")
        settled = vp.settle("customer-1", "crypto", trade["id"], 110)
        self.assertEqual(settled["result"], "win")
        accounts = vp.snapshot("customer-1")
        self.assertAlmostEqual(accounts["crypto"]["balance"], 78588.0)
        self.assertEqual(accounts["binary"]["balance"], 63578.0)
        self.assertEqual(accounts["forex"]["balance"], 13790.0)

    def test_binary_trade_cannot_settle_before_expiry(self):
        trade = vp.open_position("customer-1", "binary", "EURUSD", "CALL", 10, 1.1, 5, "binary-1")
        with self.assertRaisesRegex(ValueError, "has not expired"):
            vp.settle("customer-1", "binary", trade["id"], 1.2)

    def test_duplicate_order_reference_does_not_create_second_position(self):
        a = vp.open_position("customer-1", "forex", "EURUSD", "BUY", 100, 1.1, 5, "same-key")
        b = vp.open_position("customer-1", "forex", "EURUSD", "BUY", 100, 1.1, 5, "same-key")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(len(vp.positions("customer-1", "forex")), 1)


if __name__ == "__main__":
    unittest.main()
