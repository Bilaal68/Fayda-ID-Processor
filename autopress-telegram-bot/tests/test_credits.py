import asyncio
import unittest
import uuid
from database.database import init_db
from database.repositories.credit_repository import CreditRepository
from database.repositories.job_repository import JobRepository
from services.user_service import user_service
from services.credit_service import credit_service


class TestCredits(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    async def test_atomic_deduction_and_negative_balance_guard(self):
        """Verify credit deduction rejects overdrafts via backend."""
        from unittest.mock import patch, AsyncMock
        from services.autopress_api import autopress_api_client

        uid = 998877663
        user_service.get_or_create_user(telegram_user_id=uid)

        with patch.object(autopress_api_client, "deduct_telegram_credit", new=AsyncMock(side_effect=[
            (True, 0, None),
            (False, 0, "Insufficient credits. You have 0 credits.")
        ])):
            # Deduct 1 credit
            success, msg, new_bal = await credit_service.deduct_credit(uid, amount=1, reason="Test deduction")
            self.assertTrue(success)
            self.assertEqual(new_bal, 0)

            # Attempt to deduct with 0 balance -> must fail
            fail_success, fail_msg, bal = await credit_service.deduct_credit(uid, amount=1, reason="Overdraft test")
            self.assertFalse(fail_success)
            self.assertEqual(bal, 0)

    async def test_idempotency_guard(self):
        """Verify duplicate deduction with same job_id is idempotent."""
        from unittest.mock import patch, AsyncMock
        from services.autopress_api import autopress_api_client

        uid = 998877664
        user_service.get_or_create_user(telegram_user_id=uid)
        CreditRepository.sync_balance_snapshot(uid, 5)

        initial_bal = 5
        job_id = f"job_idempotent_{uuid.uuid4().hex[:8]}"
        JobRepository.create_job(job_id=job_id, telegram_user_id=uid)

        with patch.object(autopress_api_client, "deduct_telegram_credit", new=AsyncMock(return_value=(True, initial_bal - 1, None))):
            # First deduction
            s1, m1, b1 = await credit_service.deduct_credit(uid, amount=1, reason="Job bill", job_id=job_id)
            self.assertTrue(s1)
            self.assertEqual(b1, initial_bal - 1)

            # Second deduction with same job_id -> idempotent (no extra charge)
            s2, m2, b2 = await credit_service.deduct_credit(uid, amount=1, reason="Duplicate job bill", job_id=job_id)
            self.assertTrue(s2)
            self.assertEqual(b2, initial_bal - 1)

    async def test_backend_authoritative_balance_sync_and_fallback(self):
        """Verify credit_service queries backend API and synchronizes local snapshot."""
        from unittest.mock import patch
        from services.autopress_api import autopress_api_client

        uid = 998877665
        user_service.get_or_create_user(telegram_user_id=uid)

        # 1. When backend returns authoritative balance (e.g. 42), local cache is updated
        with patch.object(autopress_api_client, "get_telegram_balance_sync", return_value=(True, 42, None)):
            bal = credit_service.get_balance(uid)
            self.assertEqual(bal, 42)
            # Local SQLite snapshot also reflects 42
            self.assertEqual(CreditRepository.get_balance(uid), 42)

        # 2. When backend is offline/unreachable, falls back to local SQLite snapshot (42)
        with patch.object(autopress_api_client, "get_telegram_balance_sync", return_value=(False, 0, "Network error")):
            bal_fallback = credit_service.get_balance(uid)
            self.assertEqual(bal_fallback, 42)

    async def test_backend_deduction_and_refund_forwarding(self):
        """Verify credit_service forwards deductions and refunds to backend and syncs cache."""
        from unittest.mock import patch, AsyncMock
        from services.autopress_api import autopress_api_client

        uid = 998877666
        user_service.get_or_create_user(telegram_user_id=uid)
        CreditRepository.sync_balance_snapshot(uid, 10)

        # 1. Successful deduction via backend
        with patch.object(autopress_api_client, "deduct_telegram_credit", new=AsyncMock(return_value=(True, 9, None))):
            success, msg, new_bal = await credit_service.deduct_credit(uid, amount=1, reason="Test", job_id="job_1")
            self.assertTrue(success)
            self.assertEqual(new_bal, 9)
            self.assertEqual(CreditRepository.get_balance(uid), 9)

        # 2. Successful refund via backend
        with patch.object(autopress_api_client, "refund_telegram_credit", new=AsyncMock(return_value=(True, 10, None))):
            success, msg, new_bal = await credit_service.refund_credit(uid, amount=1, reason="Test refund", job_id="job_1")
            self.assertTrue(success)
            self.assertEqual(new_bal, 10)
            self.assertEqual(CreditRepository.get_balance(uid), 10)


if __name__ == "__main__":
    unittest.main()
