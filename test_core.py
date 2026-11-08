import os
import tempfile
import unittest
from pathlib import Path

DB_FILE = Path(tempfile.gettempdir()) / "numberino-python-tests.sqlite3"
os.environ["DATABASE_PATH"] = str(DB_FILE)

import bot
from fastapi.testclient import TestClient


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(str(DB_FILE) + suffix).unlink()
            except FileNotFoundError:
                pass
        bot.init_db()
        cls.client = TestClient(bot.web_app)

    def test_price_conversion(self):
        self.assertGreaterEqual(bot.price_rate("main"), 1)
        quote = bot.choose_operator({
            "one": {"cost": 1.1, "count": 2},
            "two": {"cost": 0.9, "count": 5},
        }, 600)
        self.assertEqual(quote, ("two", 540.0, 5))

    def test_jalali_date_conversion(self):
        self.assertEqual(bot.gregorian_to_jalali(2026, 3, 21), (1405, 1, 1))

    def test_available_countries(self):
        data = {"usa": {"telegram": {"any": {"cost": 1, "count": 4}}}}
        self.assertEqual(bot.available_countries(data, "telegram")[0][0], "usa")

    def test_user_and_sqlite(self):
        user = type("User", (), {"id": 991122, "username": "test_user", "first_name": "Test"})()
        bot.ensure_user("main", user)
        bot.update_user("main", user.id, balance=12000)
        self.assertEqual(float(bot.get_user("main", user.id)["balance"]), 12000)

    def test_reseller_schema(self):
        with bot.db_connect() as conn:
            conn.execute(
                "INSERT INTO reseller_bots(token,bot_username,owner_id,active,markup,channel,created_at,bot_type,parent_bot_key) "
                "VALUES(?,?,?,1,?,?,?,?,?)",
                ("test-token", "test_child_bot", 991122, 600, "", 1, "gold", "main"),
            )
        self.assertTrue(bot.is_admin(991122, "reseller:test_child_bot"))

    def test_http_health_and_api_auth(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        result = self.client.get("/api.php", params={"apikey": "invalid", "method": "getBalance"}).json()
        self.assertEqual(result["message"], "INVALID_API_KEY")
        with bot.db_connect() as conn:
            conn.execute("INSERT INTO api_keys(api_key,owner_id,balance,active,created_at) VALUES(?,?,?,?,?)",("test-api-key",991122,15000,1,1))
        result = self.client.get("/api.php", params={"apikey": "test-api-key", "method": "getBalance"}).json()
        self.assertEqual(float(result["balance"]), 15000)


if __name__ == "__main__":
    unittest.main()
