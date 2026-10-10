"""
AutoPress Backend - Admin Payment Top-Up Test Suite (Unittest)

Tests payment management, manual approval/rejection workflows,
role authorization checks, double-crediting prevention (idempotency),
and audit trail verification.
"""

import os
import unittest
import tempfile
from unittest.mock import patch, MagicMock

os.environ["SECRET_KEY"] = "test-jwt-secret-key-12345678901234567890"
os.environ["ADMIN_EMAIL"] = "bilaalm68@gmail.com"
os.environ["ADMIN_PASSWORD"] = "Admin123456!"
os.environ["TELEGRAM_BOT_TOKEN"] = ""

from app import app
import database
from models import UserModel, CreditLedgerModel, PaymentModel
from services.auth_service import hash_password, create_access_token


class TestAdminPayments(unittest.TestCase):
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

        # Regular user
        self.normal_user = UserModel.create(
            email="regular_user@example.com",
            password_hash=hash_password("User123456!"),
            full_name="Regular User",
            role="user",
            is_verified=True
        )
        self.normal_token = create_access_token(self.normal_user["id"], self.normal_user["email"], "user")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_unauthenticated_request_rejected(self):
        res = self.client.get("/api/admin/payments")
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data["status"], "error")

    def test_regular_user_forbidden(self):
        res = self.client.get(
            "/api/admin/payments",
            headers={"Authorization": f"Bearer {self.normal_token}"}
        )
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertEqual(data["status"], "error")

    def test_admin_can_access_payments_list(self):
        res = self.client.get(
            "/api/admin/payments",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("payments", data)
        self.assertIn("counts", data)

    def test_telegram_payment_submission(self):
        payload = {
            "payment_id": "pay_test12345",
            "telegram_user_id": 987654321,
            "telegram_username": "testuser",
            "package_id": "credits_20",
            "credits_requested": 20,
            "amount_etb": 200.0,
            "payment_method": "Bank Account (CBE)",
            "screenshot_file_id": "tg_file_id_receipt_abc123"
        }
        res = self.client.post("/api/payments/telegram", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["id"], "pay_test12345")
        self.assertEqual(data["data"]["status"], "PENDING")
        self.assertEqual(data["data"]["credits_requested"], 20)

    @patch("services.telegram_service.send_telegram_notification", return_value=True)
    def test_admin_payment_approval_grants_credits_atomically(self, mock_notify):
        # 1. Submit payment
        self.client.post("/api/payments/telegram", json={
            "payment_id": "pay_approval_test",
            "telegram_user_id": 11223344,
            "telegram_username": "tg_customer",
            "package_id": "credits_50",
            "credits_requested": 50,
            "amount_etb": 500.0,
            "payment_method": "Telebirr",
            "screenshot_file_id": "file_xyz"
        })

        # Check initial balance (2 welcome credits)
        tg_user = UserModel.get_by_telegram_id(11223344)
        self.assertIsNotNone(tg_user)
        initial_bal = CreditLedgerModel.get_balance(tg_user["id"])
        self.assertEqual(initial_bal, 2)

        # 2. Approve payment as Admin
        res = self.client.post(
            "/api/admin/payments/pay_approval_test/approve",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["credits_added"], 50)
        self.assertEqual(data["new_balance"], 52)

        # Verify DB state
        self.assertEqual(CreditLedgerModel.get_balance(tg_user["id"]), 52)
        payment = PaymentModel.get_by_id("pay_approval_test")
        self.assertEqual(payment["status"], "APPROVED")
        self.assertEqual(payment["reviewed_by_email"], "bilaalm68@gmail.com")

    @patch("services.telegram_service.send_telegram_notification", return_value=True)
    def test_admin_payment_double_approval_prevention_idempotency(self, mock_notify):
        """Second approval attempt must fail and NOT grant duplicate credits."""
        self.client.post("/api/payments/telegram", json={
            "payment_id": "pay_idempotency_test",
            "telegram_user_id": 55667788,
            "package_id": "credits_10",
            "credits_requested": 10,
            "amount_etb": 100.0,
            "payment_method": "Bank Account (CBE)"
        })

        tg_user = UserModel.get_by_telegram_id(55667788)

        # First approval
        res1 = self.client.post(
            "/api/admin/payments/pay_idempotency_test/approve",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(CreditLedgerModel.get_balance(tg_user["id"]), 12)

        # Second approval attempt
        res2 = self.client.post(
            "/api/admin/payments/pay_idempotency_test/approve",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res2.status_code, 400)
        data2 = res2.get_json()
        self.assertEqual(data2["status"], "error")
        self.assertIn("already been APPROVED", data2["error"])

        # CRITICAL: Verify credits are still exactly 12, NOT 22!
        self.assertEqual(CreditLedgerModel.get_balance(tg_user["id"]), 12)

    @patch("services.telegram_service.send_telegram_notification", return_value=True)
    def test_admin_payment_rejection_workflow(self, mock_notify):
        """Rejection marks payment REJECTED and adds 0 credits."""
        self.client.post("/api/payments/telegram", json={
            "payment_id": "pay_reject_test",
            "telegram_user_id": 99887766,
            "package_id": "credits_20",
            "credits_requested": 20,
            "amount_etb": 200.0,
            "payment_method": "Telebirr"
        })

        tg_user = UserModel.get_by_telegram_id(99887766)

        res = self.client.post(
            "/api/admin/payments/pay_reject_test/reject",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"reason": "Transaction reference not found in bank records"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")

        # Verify balance remains unchanged at initial welcome bonus (2)
        self.assertEqual(CreditLedgerModel.get_balance(tg_user["id"]), 2)
        payment = PaymentModel.get_by_id("pay_reject_test")
        self.assertEqual(payment["status"], "REJECTED")
        self.assertEqual(payment["rejection_reason"], "Transaction reference not found in bank records")

    @patch("services.telegram_service.fetch_telegram_receipt_image", return_value=(b"FAKE_IMAGE_BYTES", "image/jpeg"))
    def test_admin_receipt_image_proxy(self, mock_fetch_image):
        """Admin can access receipt image bytes securely."""
        self.client.post("/api/payments/telegram", json={
            "payment_id": "pay_receipt_test",
            "telegram_user_id": 44332211,
            "package_id": "credits_10",
            "credits_requested": 10,
            "amount_etb": 100.0,
            "payment_method": "Telebirr",
            "screenshot_file_id": "file_screenshot_123"
        })

        # Regular user forbidden
        res_user = self.client.get(
            "/api/admin/payments/pay_receipt_test/receipt",
            headers={"Authorization": f"Bearer {self.normal_token}"}
        )
        self.assertEqual(res_user.status_code, 403)

        # Admin authorized
        res_admin = self.client.get(
            "/api/admin/payments/pay_receipt_test/receipt",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res_admin.status_code, 200)
        self.assertEqual(res_admin.data, b"FAKE_IMAGE_BYTES")
        self.assertEqual(res_admin.mimetype, "image/jpeg")


if __name__ == "__main__":
    unittest.main()
