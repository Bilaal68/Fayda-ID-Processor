"""
AutoPress Backend - Unified User Management & Admin Manual Credits Test Suite (Unittest)

Tests:
1. Telegram user synchronization (`POST /api/user/telegram/sync`).
2. Unified Admin User listing (`GET /api/admin/users`) with search, source filtering, and status filtering.
3. Manual Admin Credit allocations (`POST /api/admin/credits` and `POST /api/admin/users/<id>/add-credits`).
4. Credit ledger audit trail verification (`ADMIN_MANUAL_CREDIT`).
5. Asynchronous Telegram notification dispatching for Telegram users.
6. Role-based authorization & security (401 unauthenticated, 403 non-admin).
"""

import os
import unittest
import tempfile
from unittest.mock import patch, MagicMock

os.environ["SECRET_KEY"] = "test-jwt-secret-key-12345678901234567890"
os.environ["ADMIN_EMAIL"] = "bilaalm68@gmail.com"
os.environ["ADMIN_PASSWORD"] = "Admin123456!"
os.environ["TELEGRAM_BOT_TOKEN"] = "test_bot_token"
os.environ["AUTOPRESS_ADMIN_BOT_SECRET"] = "test_bot_secret_super_secure_99"

from app import app
import database
from models import UserModel, CreditLedgerModel
from services.auth_service import hash_password, create_access_token


class TestAdminUsers(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_autopress.db")
        database.DB_PATH = self.db_path
        database.init_db()

        app.config["TESTING"] = True
        self.client = app.test_client()

        # Admin user
        self.admin_user = UserModel.create(
            email="bilaalm68@gmail.com",
            password_hash=hash_password("Admin123456!"),
            full_name="Bilal Admin",
            role="admin",
            is_verified=True
        )
        self.admin_token = create_access_token(self.admin_user["id"], self.admin_user["email"], "admin")

        # Regular website user
        self.normal_user = UserModel.create(
            email="regular_user@example.com",
            password_hash=hash_password("User123456!"),
            full_name="Regular Web User",
            role="user",
            is_verified=True
        )
        self.normal_token = create_access_token(self.normal_user["id"], self.normal_user["email"], "user")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_unauthenticated_user_access_rejected(self):
        res = self.client.get("/api/admin/users")
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data["status"], "error")

    def test_regular_user_forbidden_from_admin_users(self):
        res = self.client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {self.normal_token}"}
        )
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertEqual(data["status"], "error")

    def test_sync_telegram_user(self):
        # Sync a new telegram user
        sync_payload = {
            "telegram_user_id": 1806429941,
            "username": "kedija_shemsi",
            "first_name": "Kedija",
            "last_name": "Shemsi",
            "full_name": "Kedija Shemsi"
        }
        res = self.client.post("/api/user/telegram/sync", json=sync_payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["user"]["telegram_user_id"], 1806429941)
        self.assertEqual(data["user"]["source"], "telegram")
        self.assertEqual(data["user"]["current_credits"], 2)  # Welcome credits

        # Verify in database
        u = UserModel.get_by_telegram_id(1806429941)
        self.assertIsNotNone(u)
        self.assertEqual(u["telegram_username"], "kedija_shemsi")

    def test_admin_list_users_with_source_filters(self):
        # Create Telegram user
        UserModel.get_or_create_telegram_user(
            telegram_user_id=12345678,
            username="tg_user",
            first_name="Telegram",
            last_name="Tester",
            full_name="Telegram Tester"
        )

        # 1. Fetch All
        res = self.client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(data["total"], 3)  # admin, regular, telegram
        self.assertIn("counts", data)
        self.assertGreaterEqual(data["counts"]["website"], 2)
        self.assertGreaterEqual(data["counts"]["telegram"], 1)

        # 2. Filter Telegram Only
        res_tg = self.client.get(
            "/api/admin/users?source=telegram",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res_tg.status_code, 200)
        data_tg = res_tg.get_json()
        for u in data_tg["users"]:
            self.assertEqual(u["source"], "telegram")

        # 3. Filter Website Only
        res_web = self.client.get(
            "/api/admin/users?source=website",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res_web.status_code, 200)
        data_web = res_web.get_json()
        for u in data_web["users"]:
            self.assertEqual(u["source"], "website")

    def test_admin_search_users(self):
        UserModel.get_or_create_telegram_user(
            telegram_user_id=99887766,
            username="unique_tg_name",
            first_name="Special",
            last_name="Person",
            full_name="Special Person"
        )

        # Search by username
        res = self.client.get(
            "/api/admin/users?search=unique_tg_name",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["users"]), 1)
        self.assertEqual(data["users"][0]["telegram_user_id"], 99887766)

        # Search by telegram ID
        res_id = self.client.get(
            "/api/admin/users?search=99887766",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res_id.status_code, 200)
        data_id = res_id.get_json()
        self.assertEqual(len(data_id["users"]), 1)

    @patch("services.telegram_service.send_telegram_notification")
    def test_admin_add_credits_to_telegram_user(self, mock_send_tg):
        # Create Telegram user
        tg_user = UserModel.get_or_create_telegram_user(
            telegram_user_id=777888999,
            username="lucky7",
            first_name="Lucky",
            last_name="Seven",
            full_name="Lucky Seven"
        )
        initial_balance = tg_user["current_credits"]

        # Admin allocates 50 credits
        payload = {
            "user_id": tg_user["id"],
            "amount": 50,
            "action": "add",
            "reason": "Special event bonus"
        }
        res = self.client.post(
            "/api/admin/credits",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json=payload
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["balance_after"], initial_balance + 50)

        # Check user record updated
        updated_user = UserModel.get_by_id(tg_user["id"])
        self.assertEqual(updated_user["current_credits"], initial_balance + 50)

        # Verify audit ledger entry
        history, _ = CreditLedgerModel.get_history(user_id=tg_user["id"])
        self.assertTrue(any(entry["transaction_type"] == "ADMIN_MANUAL_CREDIT" and entry["amount"] == 50 for entry in history))

        # Verify telegram notification was triggered
        mock_send_tg.assert_called_once()
        args, kwargs = mock_send_tg.call_args
        chat_id = args[0] if args else kwargs.get("chat_id")
        msg_text = args[1] if len(args) > 1 else kwargs.get("text", "")
        self.assertEqual(chat_id, 777888999)
        self.assertIn("*50 credits* have been added", msg_text)
        self.assertIn(str(initial_balance + 50), msg_text)

    def test_admin_deduct_credits(self):
        initial_bal = CreditLedgerModel.get_balance(self.normal_user["id"])
        # Add 100
        CreditLedgerModel.record_transaction(
            user_id=self.normal_user["id"],
            amount=100,
            transaction_type="ADMIN_ADJUSTMENT",
            reason="Test setup"
        )
        expected_after_deduct = initial_bal + 100 - 30

        payload = {
            "user_id": self.normal_user["id"],
            "amount": 30,
            "action": "remove",
            "reason": "Administrative adjustment"
        }
        res = self.client.post(
            "/api/admin/credits",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json=payload
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["balance_after"], expected_after_deduct)

        # Verify user record updated
        updated_user = UserModel.get_by_id(self.normal_user["id"])
        self.assertEqual(updated_user["current_credits"], expected_after_deduct)

    def test_admin_service_key_authorized_access(self):
        """Admin bot secret header allows backend access without Firebase token."""
        res = self.client.get(
            "/api/admin/users",
            headers={"X-Admin-Bot-Secret": "test_bot_secret_super_secure_99"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("users", data)

    def test_admin_service_key_missing_credentials(self):
        """Request without Authorization or secret header is rejected with 401."""
        res = self.client.get("/api/admin/users")
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data["status"], "error")
        self.assertIn("Authentication required", data["error"])

    def test_admin_service_key_invalid_credentials(self):
        """Request with incorrect secret header is rejected with 401."""
        res = self.client.get(
            "/api/admin/users",
            headers={"X-Admin-Bot-Secret": "wrong_secret_123456"}
        )
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data["status"], "error")
        self.assertIn("Invalid admin bot secret", data["error"])

    def test_admin_service_key_server_unconfigured_fails_closed(self):
        """When server secret is empty or unset, request fails closed with 401."""
        with patch.dict(os.environ, {"AUTOPRESS_ADMIN_BOT_SECRET": ""}):
            res = self.client.get(
                "/api/admin/users",
                headers={"X-Admin-Bot-Secret": "test_bot_secret_super_secure_99"}
            )
            self.assertEqual(res.status_code, 401)
            data = res.get_json()
            self.assertEqual(data["status"], "error")

    def test_admin_service_key_retrieves_only_telegram_users(self):
        """Querying with source=telegram returns only Telegram bot users, not website users."""
        # 1. Create Telegram user
        UserModel.get_or_create_telegram_user(
            telegram_user_id=123456789,
            username="bot_user_1",
            first_name="Telegram",
            last_name="Tester"
        )
        # 2. Query with source=telegram using admin bot secret
        res = self.client.get(
            "/api/admin/users?source=telegram",
            headers={"X-Admin-Bot-Secret": "test_bot_secret_super_secure_99"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        users = data["users"]
        self.assertTrue(len(users) >= 1)
        # All returned users must be telegram users
        for u in users:
            self.assertEqual(u["source"], "telegram")
            self.assertIsNotNone(u["telegram_user_id"])


if __name__ == "__main__":
    unittest.main()
