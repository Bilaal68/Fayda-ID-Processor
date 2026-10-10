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
        """Verify credit deduction rejects overdrafts."""
        uid = 998877663
        user_service.get_or_create_user(telegram_user_id=uid)

        # Set balance to exactly 1
        current = credit_service.get_balance(uid)
        if current > 1:
            await credit_service.deduct_credit(uid, amount=current - 1, reason="Reset to 1")
        elif current == 0:
            credit_service.grant_credits(uid, amount=1, reason="Reset to 1")

        self.assertEqual(credit_service.get_balance(uid), 1)

        # Deduct 1 credit
        success, msg, new_bal = await credit_service.deduct_credit(uid, amount=1, reason="Test deduction")
        self.assertTrue(success)
        self.assertEqual(new_bal, 0)
        self.assertEqual(credit_service.get_balance(uid), 0)

        # Attempt to deduct with 0 balance -> must fail
        fail_success, fail_msg, bal = await credit_service.deduct_credit(uid, amount=1, reason="Overdraft test")
        self.assertFalse(fail_success)
        self.assertEqual(bal, 0)
        self.assertEqual(credit_service.get_balance(uid), 0)

    async def test_idempotency_guard(self):
        """Verify duplicate deduction with same job_id is idempotent."""
        uid = 998877664
        user_service.get_or_create_user(telegram_user_id=uid)
        credit_service.grant_credits(uid, 5, reason="Test credits")

        initial_bal = credit_service.get_balance(uid)
        job_id = f"job_idempotent_{uuid.uuid4().hex[:8]}"
        JobRepository.create_job(job_id=job_id, telegram_user_id=uid)

        # First deduction
        s1, m1, b1 = await credit_service.deduct_credit(uid, amount=1, reason="Job bill", job_id=job_id)
        self.assertTrue(s1)
        self.assertEqual(b1, initial_bal - 1)

        # Second deduction with same job_id -> must be idempotent (no extra charge)
        s2, m2, b2 = await credit_service.deduct_credit(uid, amount=1, reason="Duplicate job bill", job_id=job_id)
        self.assertTrue(s2)
        self.assertEqual(b2, initial_bal - 1)
        self.assertEqual(credit_service.get_balance(uid), initial_bal - 1)


if __name__ == "__main__":
    unittest.main()
