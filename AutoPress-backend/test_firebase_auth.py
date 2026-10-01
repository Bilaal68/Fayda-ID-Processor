import os
import sys
import unittest
from unittest.mock import patch
import io
import time

sys.path.insert(0, os.path.dirname(__file__))

from app import app
from database import init_db, db_session
from models import UserModel, CreditLedgerModel

class TestFirebaseAuthIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def test_01_missing_token_rejected(self):
        """Requests without Authorization header must be rejected with 401."""
        res = self.client.get('/api/auth/me')
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIn("Authentication required", data.get("error", ""))
        print("✅ Missing token rejected with 401")

    def test_02_invalid_firebase_token_rejected(self):
        """Invalid or corrupt Firebase tokens must be rejected with 401."""
        res = self.client.get('/api/auth/me', headers={"Authorization": "Bearer not-a-valid-token"})
        self.assertEqual(res.status_code, 401)
        print("✅ Invalid token rejected with 401")

    @patch('services.auth_service.verify_firebase_id_token')
    def test_03_firebase_user_auto_provisioned(self, mock_verify):
        """New Firebase user should be auto-provisioned in SQLite upon first request."""
        fake_uid = f"fb_uid_{int(time.time()*1000)}"
        fake_email = f"user_{fake_uid}@gmail.com"

        mock_verify.return_value = ({
            "uid": fake_uid,
            "email": fake_email,
            "name": "Firebase User",
            "email_verified": True
        }, None)

        res = self.client.post(
            '/api/auth/sync',
            headers={"Authorization": "Bearer mock-token-123"},
            json={"full_name": "Firebase User"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        user_info = data.get("user", {})
        self.assertEqual(user_info.get("email"), fake_email)
        self.assertEqual(user_info.get("firebase_uid"), fake_uid)
        self.assertEqual(user_info.get("role"), "user")
        self.assertEqual(user_info.get("status"), "active")
        print(f"✅ Firebase user successfully auto-provisioned in SQLite: ID {user_info.get('id')}")

    @patch('services.auth_service.verify_firebase_id_token')
    def test_04_existing_user_linked_by_email(self, mock_verify):
        """Existing legacy user should have their firebase_uid linked without losing credits."""
        legacy_email = f"legacy_{int(time.time()*1000)}@example.com"
        created = UserModel.create(
            email=legacy_email,
            password_hash="legacy_hash",
            full_name="Legacy User",
            role="user",
            is_verified=True
        )
        self.assertIsNotNone(created)
        legacy_id = created['id']

        # Grant 50 credits to this legacy user
        CreditLedgerModel.record_transaction(
            user_id=legacy_id,
            amount=50,
            transaction_type="ADMIN_GRANT",
            reason="Initial credits"
        )
        self.assertEqual(CreditLedgerModel.get_balance(legacy_id), 52)

        # Now user logs in with Firebase with the same email
        new_fb_uid = f"fb_uid_for_legacy_{int(time.time()*1000)}"
        mock_verify.return_value = ({
            "uid": new_fb_uid,
            "email": legacy_email,
            "name": "Legacy User Renamed",
            "email_verified": True
        }, None)

        res = self.client.get('/api/auth/me', headers={"Authorization": "Bearer mock-firebase-token"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        synced_user = data.get("user", {})

        # Verify ID and credit balance remain intact
        self.assertEqual(synced_user.get("id"), legacy_id)
        self.assertEqual(synced_user.get("firebase_uid"), new_fb_uid)
        self.assertEqual(synced_user.get("current_credits"), 52)
        print("✅ Legacy user safely linked to Firebase UID with credits preserved (Balance: 52)")

    @patch('services.auth_service.verify_firebase_id_token')
    def test_05_suspended_firebase_user_blocked(self, mock_verify):
        """Suspended users cannot access protected endpoints even with valid Firebase tokens."""
        suspended_email = f"suspended_{int(time.time()*1000)}@example.com"
        fb_uid = f"fb_suspended_{int(time.time()*1000)}"
        user = UserModel.create_or_sync_firebase_user(
            firebase_uid=fb_uid,
            email=suspended_email,
            full_name="Suspended Guy",
            is_verified=True
        )
        # Suspend user
        UserModel.update_status(user['id'], 'suspended')

        mock_verify.return_value = ({
            "uid": fb_uid,
            "email": suspended_email,
            "email_verified": True
        }, None)

        res = self.client.get('/api/auth/me', headers={"Authorization": "Bearer mock-token"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("suspended", res.get_json().get("error", "").lower())
        print("✅ Suspended user correctly rejected (401 Account Suspended)")

    @patch('services.auth_service.verify_firebase_id_token')
    def test_06_admin_role_enforcement(self, mock_verify):
        """Normal user cannot access /api/admin, but admin user can."""
        normal_uid = f"normal_{int(time.time()*1000)}"
        normal_email = f"normal_{normal_uid}@gmail.com"
        mock_verify.return_value = ({
            "uid": normal_uid,
            "email": normal_email,
            "email_verified": True
        }, None)

        # Normal user attempts admin stats
        res_normal = self.client.get('/api/admin/stats', headers={"Authorization": "Bearer mock-token"})
        self.assertEqual(res_normal.status_code, 403)
        print("✅ Normal Firebase user blocked from admin endpoints (403)")

        # Create admin user
        admin_uid = f"admin_{int(time.time()*1000)}"
        admin_email = f"admin_{admin_uid}@gmail.com"
        admin = UserModel.create_or_sync_firebase_user(
            firebase_uid=admin_uid,
            email=admin_email,
            full_name="Admin Boss",
            is_verified=True,
            role="admin"
        )
        mock_verify.return_value = ({
            "uid": admin_uid,
            "email": admin_email,
            "email_verified": True
        }, None)

        res_admin = self.client.get('/api/admin/stats', headers={"Authorization": "Bearer mock-token"})
        self.assertEqual(res_admin.status_code, 200)
        print("✅ Admin Firebase user successfully accessed /api/admin/stats (200)")

    @patch('services.auth_service.verify_firebase_id_token')
    def test_07_credit_processing_integration(self, mock_verify):
        """Document processing validates Firebase user and credits."""
        proc_uid = f"proc_uid_{int(time.time()*1000)}"
        proc_email = f"proc_{proc_uid}@gmail.com"

        user = UserModel.create_or_sync_firebase_user(
            firebase_uid=proc_uid,
            email=proc_email,
            full_name="Processor",
            is_verified=True
        )

        mock_verify.return_value = ({
            "uid": proc_uid,
            "email": proc_email,
            "email_verified": True
        }, None)

        # Drain any initial welcome credits so user has exactly 0
        init_bal = CreditLedgerModel.get_balance(user['id'])
        if init_bal > 0:
            CreditLedgerModel.record_transaction(
                user_id=user['id'],
                amount=-init_bal,
                transaction_type="ADMIN_REMOVE",
                reason="Drain initial bonus for zero-credit test"
            )

        # Zero credits should fail with 402
        res_zero = self.client.post(
            '/process-pdf-template',
            headers={"Authorization": "Bearer mock-token"},
            data={'pdf_1': (io.BytesIO(b'%PDF-1.4'), 'dummy.pdf', 'application/pdf')}
        )
        self.assertEqual(res_zero.status_code, 402)
        print("✅ Firebase user with 0 credits rejected with 402 Payment Required")

        # Grant 10 credits
        CreditLedgerModel.record_transaction(
            user_id=user['id'],
            amount=10,
            transaction_type="ADMIN_GRANT",
            reason="Top up"
        )
        self.assertEqual(CreditLedgerModel.get_balance(user['id']), 10)
        print("✅ Credits granted to Firebase user (Balance: 10)")

if __name__ == '__main__':
    unittest.main()
