"""
Unit Tests for Administrator Authorization & Rate Limiting.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from config import settings
from services.authorization import is_admin, admin_only, check_rate_limit


class TestAuthorization(unittest.IsolatedAsyncioTestCase):
    """Test suite for numeric admin authorization and rate limiter."""

    def setUp(self):
        # Configure a known admin ID for testing
        self.test_admin_id = 1806429941
        self.unauthorized_id = 999999999

    def test_is_admin_success(self):
        """Authorized numeric Telegram ID returns True."""
        with patch.object(settings, "ADMIN_TELEGRAM_IDS", (self.test_admin_id,)):
            self.assertTrue(is_admin(self.test_admin_id))

    def test_is_admin_unauthorized(self):
        """Unauthorized numeric Telegram ID returns False."""
        with patch.object(settings, "ADMIN_TELEGRAM_IDS", (self.test_admin_id,)):
            self.assertFalse(is_admin(self.unauthorized_id))

    def test_is_admin_invalid_types(self):
        """Invalid types (None, string, dict) return False."""
        with patch.object(settings, "ADMIN_TELEGRAM_IDS", (self.test_admin_id,)):
            self.assertFalse(is_admin(None))
            self.assertFalse(is_admin("1806429941"))  # type: ignore
            self.assertFalse(is_admin(0))

    async def test_admin_only_decorator_blocks_unauthorized_message(self):
        """Decorator blocks unauthorized user message and replies with access denied."""
        called = False

        @admin_only
        async def sample_handler(update, context):
            nonlocal called
            called = True

        mock_update = MagicMock()
        mock_user = MagicMock()
        mock_user.id = self.unauthorized_id
        mock_user.username = "intruder"
        mock_update.effective_user = mock_user
        mock_update.callback_query = None
        mock_update.effective_message = MagicMock()
        mock_update.effective_message.reply_text = AsyncMock()

        mock_context = MagicMock()

        with patch.object(settings, "ADMIN_TELEGRAM_IDS", (self.test_admin_id,)):
            await sample_handler(mock_update, mock_context)

        self.assertFalse(called, "Handler must NOT be executed for unauthorized user")
        mock_update.effective_message.reply_text.assert_awaited_once()
        sent_text = mock_update.effective_message.reply_text.call_args[1]["text"]
        self.assertIn("Access Denied", sent_text)

    async def test_admin_only_decorator_blocks_unauthorized_callback(self):
        """Decorator blocks unauthorized callback queries and alerts user."""
        called = False

        @admin_only
        async def sample_handler(update, context):
            nonlocal called
            called = True

        mock_update = MagicMock()
        mock_user = MagicMock()
        mock_user.id = self.unauthorized_id
        mock_update.effective_user = mock_user
        mock_update.callback_query = MagicMock()
        mock_update.callback_query.answer = AsyncMock()
        mock_update.callback_query.edit_message_text = AsyncMock()

        mock_context = MagicMock()

        with patch.object(settings, "ADMIN_TELEGRAM_IDS", (self.test_admin_id,)):
            await sample_handler(mock_update, mock_context)

        self.assertFalse(called)
        mock_update.callback_query.answer.assert_awaited_once()
        alert_msg = mock_update.callback_query.answer.call_args[0][0]
        self.assertIn("Access denied", alert_msg)

    async def test_admin_only_decorator_permits_authorized_admin(self):
        """Decorator executes handler when admin ID matches."""
        called = False

        @admin_only
        async def sample_handler(update, context):
            nonlocal called
            called = True
            return "SUCCESS"

        mock_update = MagicMock()
        mock_user = MagicMock()
        mock_user.id = self.test_admin_id
        mock_update.effective_user = mock_user

        mock_context = MagicMock()

        with patch.object(settings, "ADMIN_TELEGRAM_IDS", (self.test_admin_id,)):
            res = await sample_handler(mock_update, mock_context)

        self.assertTrue(called)
        self.assertEqual(res, "SUCCESS")

    def test_rate_limiter_cooldown(self):
        """Rate limiter prevents rapid duplicate clicks within cooldown period."""
        user_id = self.test_admin_id
        first_call = check_rate_limit(user_id, cooldown=1.0)
        second_call = check_rate_limit(user_id, cooldown=1.0)
        self.assertTrue(first_call)
        self.assertFalse(second_call, "Rapid second click must be rate-limited")


if __name__ == "__main__":
    unittest.main()

