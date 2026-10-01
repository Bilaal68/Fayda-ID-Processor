import sys
import os
import unittest
import json
import threading
import time
import io

sys.path.insert(0, os.path.dirname(__file__))

from app import app
from database import init_db
from models import UserModel, CreditLedgerModel, ProcessingRecordModel

class TestAutoPressFeatures(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        init_db()

    def test_full_auth_and_credit_flow(self):
        print("\n--- 1. Testing Registration ---")
        test_email = f"testuser_{int(time.time()*1000)}@autopress.com"
        reg_payload = {
            "full_name": "Test Ethiopian User",
            "email": test_email,
            "password": "Password123!",
            "confirm_password": "Password123!"
        }
        res = self.client.post('/api/auth/register', json=reg_payload)
        self.assertEqual(res.status_code, 201)
        reg_data = res.get_json()
        self.assertEqual(reg_data['status'], 'success')
        user_token = reg_data['token']
        user_id = reg_data['user']['id']
        print("✅ Registered user:", user_id, test_email)

        print("\n--- 2. Testing Email Verification ---")
        from services.email_service import generate_verification_token
        token = generate_verification_token(test_email)
        ver_res = self.client.post('/api/auth/verify-email', json={"token": token})
        self.assertEqual(ver_res.status_code, 200)
        user_db = UserModel.get_by_id(user_id)
        self.assertTrue(user_db['is_verified'])
        print("✅ User email verified successfully")

        print("\n--- 3. Testing Login ---")
        login_res = self.client.post('/api/auth/login', json={
            "email": test_email,
            "password": "Password123!"
        })
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.get_json()
        self.assertIn('token', login_data)
        user_token = login_data['token']
        user_headers = {"Authorization": f"Bearer {user_token}"}
        print("✅ User logged in, token received")

        print("\n--- 4. Testing User Dashboard (Initial 0 Credits) ---")
        dash_res = self.client.get('/api/user/dashboard', headers=user_headers)
        self.assertEqual(dash_res.status_code, 200)
        dash_data = dash_res.get_json()['data']
        self.assertEqual(dash_data['credits']['current_balance'], 0)
        print("✅ User dashboard loaded, balance is 0")

        print("\n--- 5. Testing Normal User Cannot Access Admin Routes ---")
        admin_stats_res = self.client.get('/api/admin/stats', headers=user_headers)
        self.assertEqual(admin_stats_res.status_code, 403)
        print("✅ Normal user blocked from admin stats (403)")

        print("\n--- 6. Testing Admin Login & Stats ---")
        admin_login_res = self.client.post('/api/auth/login', json={
            "email": "admin@autopress.com",
            "password": os.environ.get("ADMIN_PASSWORD", "Admin123456!")
        })
        self.assertEqual(admin_login_res.status_code, 200)
        admin_token = admin_login_res.get_json()['token']
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        admin_stats = self.client.get('/api/admin/stats', headers=admin_headers)
        self.assertEqual(admin_stats.status_code, 200)
        stats_data = admin_stats.get_json()['data']
        self.assertGreaterEqual(stats_data['total_users'], 1)
        print("✅ Admin accessed stats:", stats_data)

        print("\n--- 7. Admin Grants 100 Credits ---")
        grant_res = self.client.post('/api/admin/credits', headers=admin_headers, json={
            "user_id": user_id,
            "amount": 100,
            "action": "add",
            "reason": "Monthly subscription package"
        })
        self.assertEqual(grant_res.status_code, 200)
        self.assertEqual(grant_res.get_json()['new_balance'], 100)

        # Verify user sees 100 credits on dashboard
        dash_res_2 = self.client.get('/api/user/dashboard', headers=user_headers)
        self.assertEqual(dash_res_2.get_json()['data']['credits']['current_balance'], 100)
        print("✅ Admin granted 100 credits, verified on user dashboard")

        print("\n--- 8. Testing User Credit History ---")
        history_res = self.client.get('/api/user/credits/history', headers=user_headers)
        self.assertEqual(history_res.status_code, 200)
        history = history_res.get_json()['history']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['amount'], 100)
        self.assertEqual(history[0]['transaction_type'], 'ADMIN_GRANT')
        print("✅ Credit ledger verified for user")

        print("\n--- 9. Testing Processing Deduction & Refund ---")
        proc_req_id = f"test_req_{int(time.time()*1000)}"
        proc_id = ProcessingRecordModel.create(user_id, "pdf_template", 1, 1, proc_req_id)
        deduct_ok, msg, new_bal = CreditLedgerModel.record_transaction(
            user_id=user_id,
            amount=-1,
            transaction_type="PROCESSING_DEDUCTION",
            reason="Processing 1 document",
            processing_id=proc_id
        )
        self.assertTrue(deduct_ok)
        self.assertEqual(new_bal, 99)
        print("✅ Credit deducted to 99")

        # Test refund on failure
        refund_ok, rmsg, ref_bal = CreditLedgerModel.record_transaction(
            user_id=user_id,
            amount=1,
            transaction_type="PROCESSING_REFUND",
            reason="Refund for failed processing",
            processing_id=proc_id
        )
        self.assertTrue(refund_ok)
        self.assertEqual(ref_bal, 100)
        ProcessingRecordModel.mark_failed(proc_id, "Test simulation failure")
        print("✅ Automatic refund restored balance to 100")

        print("\n--- 10. Admin Deducts All Credits & Tests 0 Balance Rejection ---")
        drain_res = self.client.post('/api/admin/credits', headers=admin_headers, json={
            "user_id": user_id,
            "amount": 100,
            "action": "remove",
            "reason": "Deduct test balance"
        })
        self.assertEqual(drain_res.status_code, 200)
        self.assertEqual(drain_res.get_json()['new_balance'], 0)

        # Attempting to deduct with 0 balance must fail
        deduct_fail, fail_msg, _ = CreditLedgerModel.record_transaction(
            user_id=user_id,
            amount=-1,
            transaction_type="PROCESSING_DEDUCTION",
            reason="Document processing"
        )
        self.assertFalse(deduct_fail)
        print("✅ 0 balance deduction rejected correctly (no negative balances)")

        print("\n--- 11. Testing User Suspension ---")
        susp_res = self.client.patch(f'/api/admin/users/{user_id}/status', headers=admin_headers, json={
            "status": "suspended"
        })
        self.assertEqual(susp_res.status_code, 200)

        # Suspended user cannot access protected endpoints
        blocked_dash = self.client.get('/api/user/dashboard', headers=user_headers)
        self.assertEqual(blocked_dash.status_code, 401)
        print("✅ Suspended user blocked from dashboard")

        # Reactivate user
        react_res = self.client.patch(f'/api/admin/users/{user_id}/status', headers=admin_headers, json={
            "status": "active"
        })
        self.assertEqual(react_res.status_code, 200)
        unblocked_dash = self.client.get('/api/user/dashboard', headers=user_headers)
        self.assertEqual(unblocked_dash.status_code, 200)
        print("✅ Reactivated user successfully accesses dashboard")

        print("\n--- 12. Testing Concurrency Safety & Ledger Atomicity ---")
        CreditLedgerModel.record_transaction(user_id, 10, "ADMIN_GRANT", "Concurrency test")
        
        results = []
        def attempt_deduction():
            ok, _, _ = CreditLedgerModel.record_transaction(user_id, -1, "PROCESSING_DEDUCTION", "Race test")
            results.append(ok)

        threads = [threading.Thread(target=attempt_deduction) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        success_count = sum(1 for r in results if r is True)
        fail_count = sum(1 for r in results if r is False)
        final_bal = CreditLedgerModel.get_balance(user_id)
        
        self.assertEqual(success_count, 10)
        self.assertEqual(fail_count, 5)
        self.assertEqual(final_bal, 0)
        print(f"✅ Concurrency safe! Exactly 10 succeeded, 5 rejected, final balance is {final_bal}")

        print("\n--- 13. Testing Password Reset ---")
        from services.email_service import generate_password_reset_token
        reset_token = generate_password_reset_token(test_email)
        pw_res = self.client.post('/api/auth/reset-password', json={
            "token": reset_token,
            "password": "NewSecretPassword123!",
            "confirm_password": "NewSecretPassword123!"
        })
        self.assertEqual(pw_res.status_code, 200)

        # Login with new password
        new_login = self.client.post('/api/auth/login', json={
            "email": test_email,
            "password": "NewSecretPassword123!"
        })
        self.assertEqual(new_login.status_code, 200)
        print("✅ Password reset and subsequent login verified")

    def test_processing_endpoint_protections(self):
        print("\n--- 14. Testing Direct Processing Endpoint Protections ---")
        # 1. Unauthenticated call must be rejected with 401
        res_no_auth = self.client.post('/process-pdf-template')
        self.assertEqual(res_no_auth.status_code, 401)
        print("✅ Anonymous processing request rejected with 401 Unauthorized")

        # 2. Unverified user must be rejected with 403 (email not verified)
        unverified_email = f"unverified_{int(time.time()*1000)}@autopress.com"
        reg = self.client.post('/api/auth/register', json={
            "full_name": "Unverified User",
            "email": unverified_email,
            "password": "Password123!",
            "confirm_password": "Password123!"
        })
        unverified_token = reg.get_json()['token']
        res_unverified = self.client.post(
            '/process-pdf-template',
            headers={'Authorization': f'Bearer {unverified_token}'},
            data={'pdf_1': (io.BytesIO(b'%PDF-1.4'), 'test.pdf', 'application/pdf')}
        )
        self.assertEqual(res_unverified.status_code, 403)
        resp_data = res_unverified.get_json()
        self.assertEqual(resp_data.get('code'), 'EMAIL_NOT_VERIFIED')
        print("✅ Unverified user rejected with 403 EMAIL_NOT_VERIFIED")

        # 3. Verified user with 0 credits must be rejected with 402
        verified_email = f"zerocredit_{int(time.time()*1000)}@autopress.com"
        reg2 = self.client.post('/api/auth/register', json={
            "full_name": "Zero Balance User",
            "email": verified_email,
            "password": "Password123!",
            "confirm_password": "Password123!"
        })
        verified_token = reg2.get_json()['token']
        user_id_2 = reg2.get_json()['user']['id']

        # Verify the email so the user passes the verification gate
        from services.email_service import generate_verification_token
        verify_tok = generate_verification_token(verified_email)
        self.client.post('/api/auth/verify-email', json={"token": verify_tok})

        res_zero_credits = self.client.post(
            '/process-pdf-template',
            headers={'Authorization': f'Bearer {verified_token}'},
            data={'pdf_1': (io.BytesIO(b'%PDF-1.4'), 'test.pdf', 'application/pdf')}
        )
        self.assertEqual(res_zero_credits.status_code, 402)
        print("✅ Verified user with 0 credits rejected with 402 Payment Required")


if __name__ == '__main__':
    unittest.main()
