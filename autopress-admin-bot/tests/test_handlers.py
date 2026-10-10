"""
Unit Tests for Telegram Admin Bot Handlers.

Tests command rendering, pagination, credit adjustment validation & confirmation,
and payment approval/rejection workflows using mocked Telegram updates.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update
from config import settings
from handlers.start import command_start, command_cancel, get_main_menu_keyboard
from handlers.credits import (
    callback_start_credit_action,
    handle_credit_text_input,
    callback_confirm_credit_action
)
from handlers.payments import (
    callback_approve_confirm_prompt,
    callback_approve_execute,
    callback_reject_prompt,
    handle_payment_rejection_reason_input
)


class TestHandlers(unittest.IsolatedAsyncioTestCase):
    """Test suite for interactive Telegram bot handlers."""

    def setUp(self):
        self.admin_id = 1806429941
        self.patcher = patch.object(settings, "ADMIN_TELEGRAM_IDS", (self.admin_id,))
        self.patcher.start()
        self.rl1 = patch("handlers.credits.check_rate_limit", return_value=True)
        self.rl2 = patch("handlers.payments.check_rate_limit", return_value=True)
        self.rl1.start()
        self.rl2.start()

    def tearDown(self):
        self.rl1.stop()
        self.rl2.stop()
        self.patcher.stop()

    def _create_mock_update(self, text=None, callback_data=None):
        """Helper to create realistic mocked Update objects."""
        update = MagicMock(spec=Update)
        user = MagicMock()
        user.id = self.admin_id
        user.first_name = "Admin"
        user.username = "admin_user"
        update.effective_user = user

        if text is not None:
            msg = MagicMock()
            msg.text = text
            msg.reply_text = AsyncMock()
            update.effective_message = msg
            update.callback_query = None
        elif callback_data is not None:
            query = MagicMock()
            query.data = callback_data
            query.answer = AsyncMock()
            query.edit_message_text = AsyncMock()
            update.callback_query = query
            update.effective_message = MagicMock()
            update.effective_message.reply_text = AsyncMock()
        else:
            update.callback_query = None
            msg = MagicMock()
            msg.reply_text = AsyncMock()
            update.effective_message = msg

        return update

    async def test_start_command_renders_main_menu(self):
        """command_start renders the 10-item menu to authorized admin."""
        update = self._create_mock_update(text="/start")
        context = MagicMock()
        context.user_data = {}

        await command_start(update, context)

        update.effective_message.reply_text.assert_awaited_once()
        call_kwargs = update.effective_message.reply_text.call_args[1]
        self.assertIn("AutoPress Admin Dashboard", call_kwargs["text"])
        self.assertIsNotNone(call_kwargs["reply_markup"])

    async def test_cancel_command_clears_session(self):
        """command_cancel wipes active wizard state and returns to menu."""
        update = self._create_mock_update(text="/cancel")
        context = MagicMock()
        context.user_data = {"credit_flow": {"step": "awaiting_reason"}, "awaiting_user_search": True}

        await command_cancel(update, context)

        self.assertEqual(len(context.user_data), 0, "user_data must be cleared on /cancel")
        update.effective_message.reply_text.assert_awaited_once()
        self.assertIn("Operation Cancelled", update.effective_message.reply_text.call_args[1]["text"])

    async def test_credit_flow_validates_positive_integer_amount(self):
        """Credit flow rejects negative or non-integer amounts."""
        context = MagicMock()
        context.user_data = {
            "credit_flow": {
                "step": "awaiting_amount",
                "user_id": 85,
                "target_name": "Test User",
                "action": "add",
                "current_balance": 5
            }
        }

        # Test invalid string input
        update_invalid_str = self._create_mock_update(text="ten credits")
        await handle_credit_text_input(update_invalid_str, context)
        self.assertEqual(context.user_data["credit_flow"]["step"], "awaiting_amount")
        update_invalid_str.effective_message.reply_text.assert_awaited_once()
        self.assertIn("Invalid Amount", update_invalid_str.effective_message.reply_text.call_args[0][0])

        # Test invalid zero or negative amount
        update_zero = self._create_mock_update(text="0")
        await handle_credit_text_input(update_zero, context)
        self.assertEqual(context.user_data["credit_flow"]["step"], "awaiting_amount")

    async def test_credit_flow_negative_balance_guard(self):
        """Deducting more credits than current balance is safely rejected."""
        context = MagicMock()
        context.user_data = {
            "credit_flow": {
                "step": "awaiting_amount",
                "user_id": 85,
                "target_name": "Test User",
                "action": "remove",
                "current_balance": 4
            }
        }

        update_overdraft = self._create_mock_update(text="10")
        await handle_credit_text_input(update_overdraft, context)

        self.assertEqual(context.user_data["credit_flow"]["step"], "awaiting_amount")
        update_overdraft.effective_message.reply_text.assert_awaited_once()
        self.assertIn("Insufficient Balance", update_overdraft.effective_message.reply_text.call_args[0][0])

    async def test_credit_flow_confirmation_and_commit(self):
        """Valid amount and reason lead to explicit confirmation and successful commit."""
        context = MagicMock()
        context.user_data = {
            "credit_flow": {
                "step": "awaiting_amount",
                "user_id": 85,
                "target_name": "Test User",
                "action": "add",
                "current_balance": 10
            }
        }

        # Send valid amount
        update_amount = self._create_mock_update(text="5")
        await handle_credit_text_input(update_amount, context)
        self.assertEqual(context.user_data["credit_flow"]["step"], "awaiting_reason")
        self.assertEqual(context.user_data["credit_flow"]["amount"], 5)

        # Send valid reason
        update_reason = self._create_mock_update(text="Customer compensation for delay")
        await handle_credit_text_input(update_reason, context)
        self.assertEqual(context.user_data["credit_flow"]["step"], "awaiting_confirmation")
        self.assertEqual(context.user_data["credit_flow"]["expected_balance"], 15)

        # Click Confirm button
        update_confirm = self._create_mock_update(callback_data="credit:confirm:85")

        with patch("services.backend_client.backend_client.adjust_credits", new_callable=AsyncMock) as mock_adjust:
            mock_adjust.return_value = (True, {"new_balance": 15, "amount": 5}, None)
            await callback_confirm_credit_action(update_confirm, context)

        mock_adjust.assert_awaited_once_with(
            user_id=85,
            amount=5,
            action="add",
            reason="Customer compensation for delay"
        )
        update_confirm.callback_query.edit_message_text.assert_awaited_once()
        confirm_text = update_confirm.callback_query.edit_message_text.call_args[1]["text"]
        self.assertIn("Credit Adjustment Committed", confirm_text)
        self.assertIn("+5 credits", confirm_text)
        self.assertIn("15", confirm_text)

    async def test_payment_approval_workflow(self):
        """Payment approval asks for confirmation and commits atomically."""
        context = MagicMock()
        context.user_data = {}

        # 1. Click Approve -> Confirmation prompt
        update_prompt = self._create_mock_update(callback_data="pay:approve_confirm:pay_999")
        mock_payment = {
            "id": "pay_999",
            "status": "PENDING",
            "amount_etb": 200.0,
            "credits_requested": 20,
            "telegram_user_id": 1806429941
        }

        with patch("services.backend_client.backend_client.get_payment_detail", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = (True, {"data": mock_payment}, None)
            await callback_approve_confirm_prompt(update_prompt, context)

        update_prompt.callback_query.edit_message_text.assert_awaited_once()
        self.assertIn("CONFIRM PAYMENT APPROVAL", update_prompt.callback_query.edit_message_text.call_args[1]["text"])

        # 2. Click Yes, Confirm -> Commits through backend
        update_commit = self._create_mock_update(callback_data="pay:approve_do:pay_999")
        with patch("services.backend_client.backend_client.approve_payment", new_callable=AsyncMock) as mock_approve:
            mock_approve.return_value = (True, {"new_balance": 35, "credits_added": 20}, None)
            await callback_approve_execute(update_commit, context)

        mock_approve.assert_awaited_once_with("pay_999")
        update_commit.callback_query.edit_message_text.assert_awaited_once()
        success_text = update_commit.callback_query.edit_message_text.call_args[1]["text"]
        self.assertIn("Payment Approved Successfully", success_text)
        self.assertIn("+20 credits", success_text)

    async def test_payment_rejection_workflow(self):
        """Payment rejection prompts for reason and records it."""
        context = MagicMock()
        context.user_data = {}

        # 1. Prompt for rejection reason
        update_prompt = self._create_mock_update(callback_data="pay:reject_prompt:pay_999")
        await callback_reject_prompt(update_prompt, context)

        self.assertIn("payment_reject_flow", context.user_data)
        self.assertEqual(context.user_data["payment_reject_flow"]["payment_id"], "pay_999")

        # 2. Send reason message
        update_reason = self._create_mock_update(text="Invalid screenshot submitted")
        with patch("services.backend_client.backend_client.reject_payment", new_callable=AsyncMock) as mock_reject:
            mock_reject.return_value = (True, {"status": "success"}, None)
            await handle_payment_rejection_reason_input(update_reason, context)

        reply_call = update_reason.effective_message.reply_text.call_args
        sent_msg = reply_call[1].get("text") or (reply_call[0][0] if reply_call[0] else "")
        self.assertIn("Payment Rejected", sent_msg)


if __name__ == "__main__":
    unittest.main()
