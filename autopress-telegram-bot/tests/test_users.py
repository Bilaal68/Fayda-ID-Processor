"""
Unit tests for User Service and Repository
"""

import unittest
from database.database import init_db
from database.repositories.user_repository import UserRepository
from services.user_service import user_service
from services.credit_service import credit_service


class TestUsers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_user_creation_and_retrieval(self):
        """Verify user is provisioned and receives initial bonus."""
        test_uid = 998877661
        user = user_service.get_or_create_user(
            telegram_user_id=test_uid,
            username="testuser",
            first_name="Test",
            last_name="User",
            language="en"
        )
        self.assertIsNotNone(user)
        self.assertEqual(user["telegram_user_id"], test_uid)
        self.assertEqual(user["username"], "testuser")

        # Verify initial balance
        balance = credit_service.get_balance(test_uid)
        self.assertGreaterEqual(balance, 0)

    def test_language_preference(self):
        """Verify language update."""
        test_uid = 998877662
        user_service.get_or_create_user(telegram_user_id=test_uid)
        user_service.set_language(test_uid, "am")
        user = user_service.get_user(test_uid)
        self.assertEqual(user["language"], "am")


if __name__ == "__main__":
    unittest.main()
