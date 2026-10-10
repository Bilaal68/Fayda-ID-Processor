"""
AutoPress Backend - Telegram Credit Synchronization & Ledger Test Suite

Tests authoritative balance retrieval, deduction, refund, payment approval,
service secret authentication, and PDF template deduction bypass.
"""

import os
import io
import unittest
import tempfile
from unittest.mock import patch, MagicMock

os.environ["SECRET_KEY"] = "test-jwt-secret-key-12345678901234567890"
os.environ["ADMIN_EMAIL"] = "bilaalm68@gmail.com"
os.environ["ADMIN_PASSWORD"] = "Admin123456!"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["AUTOPRESS_SERVICE_SECRET"] = "test-service-secret-xyz"
os.environ["AUTOPRESS_ADMIN_BOT_SECRET"] = "test-admin-bot-secret-xyz"

from app import app
import database
from models import UserModel, CreditLedgerModel, PaymentModel
from services.auth_service import hash_password, create_access_token


class TestTelegramCreditsAPI(unittest.TestCase):
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
        self.service_secret = "test-service-secret-xyz"
        self.admin_bot_secret = "test-admin-bot-secret-xyz"
        os.environ["AUTOPRESS_SERVICE_SECRET"] = self.service_secret
        os.environ["AUTOPRESS_ADMIN_BOT_SECRET"] = self.admin_bot_secret
        self.headers = {"X-Service-Secret": self.service_secret}

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_service_secret_authentication_required(self):
        """Endpoints under /api/user/telegram require valid service secret."""
        tg_id = 111222333

        # 1. Missing secret -> 401
        res = self.client.get(f"/api/user/telegram/{tg_id}/balance")
        self.assertEqual(res.status_code, 401)
        self.assertIn("required", res.get_json()["error"])

        # 2. Invalid secret -> 403
        res = self.client.get(
            f"/api/user/telegram/{tg_id}/balance",
            headers={"X-Service-Secret": "invalid-secret-value"}
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Invalid", res.get_json()["error"])

        # 3. Valid X-Service-Secret -> 200
        res = self.client.get(
            f"/api/user/telegram/{tg_id}/balance",
            headers={"X-Service-Secret": self.service_secret}
        )
        self.assertEqual(res.status_code, 200)

        # 4. Valid X-Admin-Bot-Secret -> 200
        res = self.client.get(
            f"/api/user/telegram/{tg_id}/balance",
            headers={"X-Admin-Bot-Secret": self.admin_bot_secret}
        )
        self.assertEqual(res.status_code, 200)

    def test_get_telegram_balance_creates_and_returns_balance(self):
        """GET /api/user/telegram/<tg_id>/balance should auto-provision and return initial balance."""
        tg_id = 123456789
        res = self.client.get(f"/api/user/telegram/{tg_id}/balance", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["telegram_user_id"], tg_id)
        # Default signup credits is 2
        self.assertEqual(data["balance"], 2)

    def test_deduct_and_refund_telegram_credit_with_idempotency(self):
        """POST /api/user/telegram/<tg_id>/deduct & refund with job_id idempotency."""
        tg_id = 987654321
        # 1. Initial balance check
        res = self.client.get(f"/api/user/telegram/{tg_id}/balance", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["balance"], 2)

        # 2. Deduct 1 credit with job_id
        job_id = "job_test_12345"
        res = self.client.post(
            f"/api/user/telegram/{tg_id}/deduct",
            headers=self.headers,
            json={"amount": 1, "reason": "Fayda PDF Processing", "job_id": job_id}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["new_balance"], 1)

        # 3. Duplicate deduction with same job_id -> idempotent (balance unchanged)
        res_dup = self.client.post(
            f"/api/user/telegram/{tg_id}/deduct",
            headers=self.headers,
            json={"amount": 1, "reason": "Fayda PDF Processing", "job_id": job_id}
        )
        self.assertEqual(res_dup.status_code, 200)
        self.assertEqual(res_dup.get_json()["new_balance"], 1)

        # 4. Deduct second credit
        res2 = self.client.post(
            f"/api/user/telegram/{tg_id}/deduct",
            headers=self.headers,
            json={"amount": 1, "reason": "Fayda PDF Processing 2", "job_id": "job_test_67890"}
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()["new_balance"], 0)

        # 5. Deduct when balance is 0 -> should fail with 400 Insufficient credits
        res_fail = self.client.post(
            f"/api/user/telegram/{tg_id}/deduct",
            headers=self.headers,
            json={"amount": 1, "reason": "Fayda PDF Processing 3"}
        )
        self.assertEqual(res_fail.status_code, 400)
        self.assertIn("Insufficient credits", res_fail.get_json()["error"])

        # 6. Refund 1 credit with job_id
        res_ref = self.client.post(
            f"/api/user/telegram/{tg_id}/refund",
            headers=self.headers,
            json={"amount": 1, "reason": "Processing failure refund", "job_id": "job_fail_1"}
        )
        self.assertEqual(res_ref.status_code, 200)
        self.assertEqual(res_ref.get_json()["new_balance"], 1)

        # 7. Duplicate refund with same job_id -> idempotent
        res_ref_dup = self.client.post(
            f"/api/user/telegram/{tg_id}/refund",
            headers=self.headers,
            json={"amount": 1, "reason": "Processing failure refund", "job_id": "job_fail_1"}
        )
        self.assertEqual(res_ref_dup.status_code, 200)
        self.assertEqual(res_ref_dup.get_json()["new_balance"], 1)

    @patch("services.telegram_service.send_telegram_notification")
    def test_payment_approval_increases_telegram_user_balance(self, mock_notify):
        """Submitting payment and approving via admin endpoint updates Telegram user balance."""
        mock_notify.return_value = True
        tg_id = 555444333

        # 1. Submit payment
        pay_res = self.client.post(
            "/api/payments/telegram",
            headers=self.headers,
            json={
                "payment_id": "pay_tg_test_100",
                "telegram_user_id": tg_id,
                "telegram_username": "tg_tester",
                "package_id": "credits_20",
                "credits_requested": 20,
                "amount_etb": 200.0,
                "payment_method": "Commercial Bank of Ethiopia (CBE)"
            }
        )
        self.assertEqual(pay_res.status_code, 201)

        # 2. Check balance before approval (default signup is 2)
        bal_res = self.client.get(f"/api/user/telegram/{tg_id}/balance", headers=self.headers)
        self.assertEqual(bal_res.get_json()["balance"], 2)

        # 3. Admin approves payment using X-Admin-Bot-Secret
        app_res = self.client.post(
            "/api/admin/payments/pay_tg_test_100/approve",
            headers={"X-Admin-Bot-Secret": self.service_secret}
        )
        self.assertEqual(app_res.status_code, 200)
        res_data = app_res.get_json()
        self.assertEqual(res_data["new_balance"], 22)  # 2 + 20 = 22
        self.assertTrue(res_data["notification_sent"])

        # 4. Telegram user balance reflects the approved credits immediately
        bal_res2 = self.client.get(f"/api/user/telegram/{tg_id}/balance", headers=self.headers)
        self.assertEqual(bal_res2.get_json()["balance"], 22)

        # 5. Second approval attempt fails idempotently
        app_res2 = self.client.post(
            "/api/admin/payments/pay_tg_test_100/approve",
            headers={"X-Admin-Bot-Secret": self.service_secret}
        )
        self.assertEqual(app_res2.status_code, 400)
        self.assertIn("already been APPROVED", app_res2.get_json()["error"])
        # Balance remains 22, no duplicate credits added
        bal_res3 = self.client.get(f"/api/user/telegram/{tg_id}/balance", headers=self.headers)
        self.assertEqual(bal_res3.get_json()["balance"], 22)

    @patch("services.telegram_service.send_telegram_notification")
    def test_admin_manual_credit_add_reflects_in_telegram_balance(self, mock_notify):
        """Admin manually granting credits via /api/admin/credits updates Telegram balance."""
        tg_id = 777888999
        # Provision user
        user = UserModel.get_or_create_telegram_user(telegram_user_id=tg_id, username="manual_tg")
        user_id = user["id"]

        # Admin adds credits using X-Admin-Bot-Secret
        add_res = self.client.post(
            "/api/admin/credits",
            headers={"X-Admin-Bot-Secret": self.service_secret},
            json={
                "user_id": user_id,
                "amount": 15,
                "action": "add",
                "reason": "Customer loyalty bonus"
            }
        )
        self.assertEqual(add_res.status_code, 200)
        self.assertEqual(add_res.get_json()["new_balance"], 17)  # 2 default + 15 = 17

        # Balance query returns 17
        bal_res = self.client.get(f"/api/user/telegram/{tg_id}/balance", headers=self.headers)
        self.assertEqual(bal_res.get_json()["balance"], 17)

    @patch("services.gemini.extract_from_pdf")
    @patch("routes.fayda.generate_final_png")
    def test_process_pdf_template_bypasses_admin_deduction_with_service_secret(
        self, mock_generate_png, mock_extract_pdf
    ):
        """Requests with valid service secret bypass deduction from admin account (user 1)."""
        mock_extract_pdf.return_value = ({"Name": "Abebe"}, "base64_photo", "base64_qr")
        mock_generate_png.return_value = b"fake_lossless_png_bytes"

        # Give admin 5 credits initially
        admin_id = self.admin_user["id"]
        CreditLedgerModel.record_transaction(
            user_id=admin_id, amount=5, transaction_type="ADMIN_SEED", reason="Seed credits"
        )
        self.assertEqual(CreditLedgerModel.get_balance(admin_id), 5)

        # Submit PDF with Service Secret header
        data = {
            "pdf_1": (io.BytesIO(b"%PDF-1.4 test content"), "test_fayda.pdf", "application/pdf")
        }
        res = self.client.post(
            "/process-pdf-template",
            headers={
                "X-Service-Secret": self.service_secret,
                "Authorization": f"Bearer {self.admin_token}"
            },
            data=data,
            content_type="multipart/form-data"
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, b"fake_lossless_png_bytes")
        # Admin balance must STILL be 5 (deduction bypassed!)
        self.assertEqual(CreditLedgerModel.get_balance(admin_id), 5)

    @patch("services.gemini.extract_from_pdf")
    @patch("routes.fayda.generate_final_png")
    def test_process_pdf_template_enforces_deduction_without_service_secret(
        self, mock_generate_png, mock_extract_pdf
    ):
        """Website requests without service secret enforce deduction from the authenticated user."""
        mock_extract_pdf.return_value = ({"Name": "Kebede"}, "base64_photo", "base64_qr")
        mock_generate_png.return_value = b"fake_lossless_png_bytes"

        # Create a regular web user with verified email
        web_user = UserModel.create(
            email="webuser@autopress.com",
            password_hash=hash_password("User123456!"),
            full_name="Web User",
            role="user",
            is_verified=True
        )
        web_uid = web_user["id"]
        web_token = create_access_token(web_uid, web_user["email"], "user")

        initial_bal = CreditLedgerModel.get_balance(web_uid)
        self.assertGreaterEqual(initial_bal, 1)

        # Call /process-pdf-template WITHOUT service secret
        data = {
            "pdf_1": (io.BytesIO(b"%PDF-1.4 test content"), "test_fayda.pdf", "application/pdf")
        }
        res = self.client.post(
            "/process-pdf-template",
            headers={"Authorization": f"Bearer {web_token}"},
            data=data,
            content_type="multipart/form-data"
        )

        self.assertEqual(res.status_code, 200)
        # Web user balance must be reduced by exactly 1
        self.assertEqual(CreditLedgerModel.get_balance(web_uid), initial_bal - 1)


if __name__ == "__main__":
    unittest.main()
