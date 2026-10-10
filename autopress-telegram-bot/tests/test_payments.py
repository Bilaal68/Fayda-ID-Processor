"""
Unit and Integration Tests for Payments & Top-Up System
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Message, CallbackQuery, Document, PhotoSize
from telegram.ext import ContextTypes

from config import CREDIT_PACKAGES, settings
from database.database import init_db, get_connection
from database.repositories.credit_repository import CreditRepository
from database.repositories.payment_repository import PaymentRepository
from database.repositories.user_repository import UserRepository
from services.payment_service import payment_service, PaymentService
from handlers.credits import (
    credits_handler,
    topup_init_handler,
    package_selected_handler,
    payment_method_selected_handler,
    payment_screenshot_handler,
    admin_payment_callback_handler,
    topup_back_handler,
    my_payments_handler,
)
from states.conversation_states import ConversationState


class TestPaymentSystem(unittest.IsolatedAsyncioTestCase):
    """Test suite for manual credit top-up payments and admin workflows."""

    def setUp(self):
        init_db()
        self.user_id = 998877800
        UserRepository.get_or_create_user(
            telegram_user_id=self.user_id,
            username="test_payer",
            first_name="Test",
            last_name="Payer"
        )
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM credit_transactions WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = ?)", (self.user_id,))
            cursor.execute("DELETE FROM payment_receipts WHERE telegram_user_id = ?", (self.user_id,))

    def test_payment_request_creation(self):
        """Test creating a PENDING payment request."""
        payment = payment_service.create_payment_request(
            telegram_user_id=self.user_id,
            package_id="credits_20",
            payment_method="Bank Account (CBE)",
            screenshot_file_id="photo_file_12345"
        )

        self.assertIsNotNone(payment)
        self.assertEqual(payment["status"], "PENDING")
        self.assertEqual(payment["credits_requested"], 20)
        self.assertEqual(payment["amount_etb"], 200.0)
        self.assertEqual(payment["payment_method"], "Bank Account (CBE)")
        self.assertEqual(payment["screenshot_file_id"], "photo_file_12345")

        # Verify user balance remains 0
        bal = CreditRepository.get_balance(self.user_id)
        self.assertEqual(bal, 0)

    def test_admin_approve_payment_success_and_idempotency(self):
        """Test admin approving a payment request and ensuring idempotency."""
        payment = payment_service.create_payment_request(
            telegram_user_id=self.user_id,
            package_id="credits_50",
            payment_method="Telebirr",
            screenshot_file_id="photo_file_50"
        )
        payment_id = payment["id"]

        # First approval: Success
        success, msg, updated_payment, new_balance = payment_service.approve_payment(
            payment_id=payment_id,
            admin_id=7246416805
        )

        self.assertTrue(success)
        self.assertEqual(new_balance, 50)
        self.assertEqual(updated_payment["status"], "APPROVED")

        # Verify balance in database
        bal = CreditRepository.get_balance(self.user_id)
        self.assertEqual(bal, 50)

        # Second approval: Must fail with idempotency guard
        success2, msg2, updated_payment2, new_balance2 = payment_service.approve_payment(
            payment_id=payment_id,
            admin_id=7246416805
        )
        self.assertFalse(success2)
        self.assertIn("already", msg2.lower())

        # Balance still 50
        self.assertEqual(CreditRepository.get_balance(self.user_id), 50)

    def test_admin_reject_payment(self):
        """Test admin rejecting a payment request."""
        payment = payment_service.create_payment_request(
            telegram_user_id=self.user_id,
            package_id="credits_10",
            payment_method="Bank Account (CBE)",
            screenshot_file_id="photo_file_10"
        )
        payment_id = payment["id"]

        success, msg, updated_payment = payment_service.reject_payment(
            payment_id=payment_id,
            admin_id=7246416805
        )

        self.assertTrue(success)
        self.assertEqual(updated_payment["status"], "REJECTED")

        # Balance remains 0
        bal = CreditRepository.get_balance(self.user_id)
        self.assertEqual(bal, 0)

    def test_user_payment_history(self):
        """Test fetching a user's payment history."""
        payment_service.create_payment_request(
            telegram_user_id=self.user_id,
            package_id="credits_10",
            payment_method="Bank Account (CBE)"
        )
        payment_service.create_payment_request(
            telegram_user_id=self.user_id,
            package_id="credits_20",
            payment_method="Telebirr"
        )

        history = payment_service.get_user_payments(self.user_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["package_id"], "credits_20")
        self.assertEqual(history[1]["package_id"], "credits_10")

    async def test_balance_and_topup_ui_flow(self):
        """Test full button-driven UI flow: Balance -> TopUp -> Select Package -> Payment Method -> Back."""
        # 1. Balance Screen
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User, id=self.user_id, username="test_payer", first_name="Test", last_name="Payer")
        update.effective_message = MagicMock(spec=Message)
        update.effective_message.reply_text = AsyncMock()

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}

        await credits_handler(update, context)
        update.effective_message.reply_text.assert_called_once()
        balance_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("AutoPress Balance", balance_text)
        self.assertIn("Credits: 0", balance_text)
        self.assertIn("Top up your balance below", balance_text)

        # 2. Press TOP UP CREDITS
        update.effective_message.reply_text.reset_mock()
        await topup_init_handler(update, context)
        update.effective_message.reply_text.assert_called_once()
        topup_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Choose a Credit Package", topup_text)
        self.assertIn("10 Credits — 100 ETB", topup_text)
        self.assertEqual(context.user_data["state"], ConversationState.WAITING_FOR_PACKAGE_SELECTION.name)

        # 3. Select Package (10 Credits — 100 ETB)
        update.effective_message.reply_text.reset_mock()
        update.effective_message.text = "10 Credits — 100 ETB"
        await package_selected_handler(update, context)
        update.effective_message.reply_text.assert_called_once()
        pkg_selected_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("You selected:", pkg_selected_text)
        self.assertIn("10 Credits — 100 ETB", pkg_selected_text)
        self.assertIn("Choose Payment Method", pkg_selected_text)
        self.assertEqual(context.user_data["selected_package"], "credits_10")
        self.assertEqual(context.user_data["state"], ConversationState.WAITING_FOR_PAYMENT_METHOD.name)

        # 4. Back button from Payment Method -> Returns to Package Selection preserving context
        update.effective_message.reply_text.reset_mock()
        await topup_back_handler(update, context)
        update.effective_message.reply_text.assert_called_once()
        back_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Choose a Credit Package", back_text)
        self.assertEqual(context.user_data["state"], ConversationState.WAITING_FOR_PACKAGE_SELECTION.name)
        self.assertEqual(context.user_data["selected_package"], "credits_10")

        # 5. Back button from Package Selection -> Returns to Balance Screen
        update.effective_message.reply_text.reset_mock()
        await topup_back_handler(update, context)
        update.effective_message.reply_text.assert_called_once()
        back_bal_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("AutoPress Balance", back_bal_text)
        self.assertEqual(context.user_data["state"], ConversationState.IDLE.name)


if __name__ == "__main__":
    unittest.main()
