"""
Unit tests for Telegram Bot Handlers, Menus, and Credit Purchase Flow
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import re
from handlers import register_handlers
from keyboards import (
    get_main_menu_keyboard,
    get_balance_keyboard,
    get_packages_keyboard,
    get_payment_methods_keyboard,
    get_payment_waiting_keyboard,
    get_cancel_keyboard,
)
from states.conversation_states import ConversationState
from telegram.ext import ApplicationBuilder


class TestHandlers(unittest.IsolatedAsyncioTestCase):
    def test_handler_registration(self):
        """Verify handlers register without error on Application."""
        app = ApplicationBuilder().token("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11").build()
        register_handlers(app)
        self.assertGreater(len(app.handlers[0]), 0)

    def test_main_menu_keyboard_structure(self):
        """Verify persistent main menu keyboard contains all 8 requested buttons."""
        kb = get_main_menu_keyboard()
        self.assertTrue(getattr(kb, "is_persistent", False))
        self.assertTrue(kb.resize_keyboard)

        # Expected 4 rows x 2 columns
        self.assertEqual(len(kb.keyboard), 4)
        buttons = [[btn.text for btn in row] for row in kb.keyboard]
        self.assertEqual(buttons[0], ["📸 Upload / Process ID", "💳 Balance"])
        self.assertEqual(buttons[1], ["🛒 Buy Credits", "📋 My Jobs"])
        self.assertEqual(buttons[2], ["👤 My Profile", "🌐 Language"])
        self.assertEqual(buttons[3], ["ℹ️ Help", "❌ Cancel"])

    def test_sub_keyboards_structure(self):
        """Verify packages and cancel keyboards have proper navigation actions."""
        pkg_kb = get_packages_keyboard()
        pkg_texts = [btn.text for row in pkg_kb.keyboard for btn in row]
        self.assertIn("10 Credits — 100 ETB", pkg_texts)
        self.assertIn("20 Credits — 200 ETB", pkg_texts)
        self.assertIn("50 Credits — 500 ETB", pkg_texts)
        self.assertIn("100 Credits — 1,000 ETB", pkg_texts)
        self.assertIn("⬅️ Back", pkg_texts)
        self.assertIn("🏠 Back to Menu", pkg_texts)
        self.assertIn("❌ Cancel", pkg_texts)

        cancel_kb = get_cancel_keyboard()
        cancel_texts = [btn.text for row in cancel_kb.keyboard for btn in row]
        self.assertIn("🏠 Back to Menu", cancel_texts)
        self.assertIn("❌ Cancel", cancel_texts)

    def test_button_regex_matching(self):
        """Verify button regexes match all variations used in UI (both new and legacy)."""
        # 1. Upload buttons
        upload_pattern = re.compile(r"(?i)^(📸\s*Upload\s*(/\s*Process\s*ID)?|📤\s*Upload)$")
        self.assertTrue(upload_pattern.match("📸 Upload / Process ID"))
        self.assertTrue(upload_pattern.match("📸 Upload"))
        self.assertTrue(upload_pattern.match("📤 Upload"))

        # 2. Balance buttons
        balance_pattern = re.compile(r"(?i)^(💳\s*Balance|💰\s*Balance)$")
        self.assertTrue(balance_pattern.match("💳 Balance"))
        self.assertTrue(balance_pattern.match("💳 balance"))
        self.assertTrue(balance_pattern.match("💰 Balance"))
        self.assertTrue(balance_pattern.match("💰 balance"))

        # 3. Buy Credits / Top-Up buttons
        buy_pattern = re.compile(r"(?i)^(🛒\s*Buy\s*Credits|💳\s*Top[- ]?Up(\s*Credits)?)$")
        self.assertTrue(buy_pattern.match("🛒 Buy Credits"))
        self.assertTrue(buy_pattern.match("💳 TOP UP CREDITS"))
        self.assertTrue(buy_pattern.match("💳 Top-Up Credits"))
        self.assertTrue(buy_pattern.match("💳 Top Up"))

        # 4. Jobs / History buttons
        jobs_pattern = re.compile(r"(?i)^(📋\s*My\s*Jobs|📜\s*History)$")
        self.assertTrue(jobs_pattern.match("📋 My Jobs"))
        self.assertTrue(jobs_pattern.match("📜 History"))

        # 5. Profile buttons
        profile_pattern = re.compile(r"(?i)^(👤\s*My\s*Profile|👤\s*Profile)$")
        self.assertTrue(profile_pattern.match("👤 My Profile"))
        self.assertTrue(profile_pattern.match("👤 Profile"))

        # 6. Language button
        lang_pattern = re.compile(r"(?i)^🌐\s*Language$")
        self.assertTrue(lang_pattern.match("🌐 Language"))

        # 7. Help buttons
        help_pattern = re.compile(r"(?i)^(ℹ️\s*Help|❓\s*Help)$")
        self.assertTrue(help_pattern.match("ℹ️ Help"))
        self.assertTrue(help_pattern.match("❓ Help"))

        # 8. Cancel buttons
        cancel_pattern = re.compile(r"(?i)^(❌\s*Cancel|Cancel)$")
        self.assertTrue(cancel_pattern.match("❌ Cancel"))
        self.assertTrue(cancel_pattern.match("Cancel"))

        # 9. Main Menu & Back buttons
        menu_pattern = re.compile(r"(?i)^(🏠\s*Main\s*Menu|Main\s*Menu|Menu|🏠\s*Back\s*to\s*Menu)$")
        self.assertTrue(menu_pattern.match("🏠 Main Menu"))
        self.assertTrue(menu_pattern.match("Main Menu"))
        self.assertTrue(menu_pattern.match("Menu"))
        self.assertTrue(menu_pattern.match("🏠 Back to Menu"))

        back_pattern = re.compile(r"(?i)^⬅️\s*Back$")
        self.assertTrue(back_pattern.match("⬅️ Back"))

        # 10. Package buttons
        pkg_pattern = re.compile(r"(?i)^\d+\s*Credits\s*—\s*[\d,]+\s*ETB$")
        self.assertTrue(pkg_pattern.match("10 Credits — 100 ETB"))
        self.assertTrue(pkg_pattern.match("20 Credits — 200 ETB"))
        self.assertTrue(pkg_pattern.match("50 Credits — 500 ETB"))
        self.assertTrue(pkg_pattern.match("100 Credits — 1,000 ETB"))

        # 11. Payment method buttons
        pm_pattern = re.compile(r"(?i)^(🏦\s*Bank\s*Account|📱\s*Telebirr)")
        self.assertTrue(pm_pattern.match("🏦 Bank Account"))
        self.assertTrue(pm_pattern.match("📱 Telebirr"))

    # -----------------------------------------------------------------------
    # Handler Flow Tests using Mocks
    # -----------------------------------------------------------------------

    def _create_mock_update_context(self, user_id=123456, text=None):
        """Helper to create mock Telegram Update and Context objects."""
        update = MagicMock()
        update.effective_user.id = user_id
        update.effective_user.username = "tester"
        update.effective_user.first_name = "Test"
        update.effective_user.last_name = "User"
        update.effective_user.full_name = "Test User"
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.text = text
        update.effective_message.photo = []
        update.effective_message.document = None

        context = MagicMock()
        context.user_data = {}
        context.bot.send_photo = AsyncMock()
        context.bot.send_message = AsyncMock()
        return update, context

    @patch("handlers.start.credit_service.get_balance", return_value=5)
    @patch("handlers.start.user_service.get_or_create_user")
    async def test_start_flow_displays_main_menu(self, mock_user, mock_balance):
        """Verify /start displays welcome message and persistent main menu."""
        from handlers.start import start_handler
        update, context = self._create_mock_update_context()

        await start_handler(update, context)

        self.assertEqual(context.user_data.get("state"), ConversationState.IDLE.name)
        update.effective_message.reply_text.assert_called_once()
        _, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("reply_markup", kwargs)
        # Verify reply markup is main menu
        kb = kwargs["reply_markup"]
        btn_texts = [btn.text for row in kb.keyboard for btn in row]
        self.assertIn("📸 Upload / Process ID", btn_texts)
        self.assertIn("🛒 Buy Credits", btn_texts)

    @patch("handlers.credits.credit_service.get_balance", return_value=7)
    @patch("handlers.credits.user_service.get_or_create_user")
    async def test_balance_handler_displays_current_balance(self, mock_user, mock_balance):
        """Verify Balance button displays user balance and main menu keyboard."""
        from handlers.credits import credits_handler
        update, context = self._create_mock_update_context()

        await credits_handler(update, context)

        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("Credits: 7", args[0])
        self.assertIn("🛒 Buy Credits", args[0])
        self.assertIn("reply_markup", kwargs)

    @patch("handlers.credits.user_service.get_or_create_user")
    async def test_buy_credits_opens_package_selection_directly(self, mock_user):
        """Verify Buy Credits opens package selection directly without opening Balance."""
        from handlers.credits import topup_init_handler
        update, context = self._create_mock_update_context()

        await topup_init_handler(update, context)

        self.assertEqual(context.user_data.get("state"), ConversationState.WAITING_FOR_PACKAGE_SELECTION.name)
        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("Choose a Credit Package", args[0])
        # Keyboard must be packages keyboard
        kb = kwargs["reply_markup"]
        btn_texts = [btn.text for row in kb.keyboard for btn in row]
        self.assertIn("10 Credits — 100 ETB", btn_texts)

    async def test_package_selection_to_payment_method(self):
        """Verify choosing a package moves state to WAITING_FOR_PAYMENT_METHOD."""
        from handlers.credits import package_selected_handler
        update, context = self._create_mock_update_context(text="20 Credits — 200 ETB")
        context.user_data["state"] = ConversationState.WAITING_FOR_PACKAGE_SELECTION.name

        await package_selected_handler(update, context)

        self.assertEqual(context.user_data.get("selected_package"), "credits_20")
        self.assertEqual(context.user_data.get("state"), ConversationState.WAITING_FOR_PAYMENT_METHOD.name)
        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("Choose Payment Method", args[0])

    async def test_payment_method_selection_to_screenshot_waiting(self):
        """Verify choosing payment method presents instructions and moves to WAITING_FOR_PAYMENT_SCREENSHOT."""
        from handlers.credits import payment_method_selected_handler
        update, context = self._create_mock_update_context(text="🏦 Bank Account")
        context.user_data["selected_package"] = "credits_10"
        context.user_data["state"] = ConversationState.WAITING_FOR_PAYMENT_METHOD.name

        await payment_method_selected_handler(update, context)

        self.assertEqual(context.user_data.get("payment_method"), "Bank Account (CBE)")
        self.assertEqual(context.user_data.get("state"), ConversationState.WAITING_FOR_PAYMENT_SCREENSHOT.name)
        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("Bank Transfer Details", args[0])

    @patch("handlers.credits.payment_service.create_payment_request")
    async def test_receipt_submission_workflow(self, mock_create_payment):
        """Verify submitting screenshot creates pending payment and resets state to IDLE."""
        from handlers.credits import payment_screenshot_handler
        mock_create_payment.return_value = {
            "id": "pay_mock123",
            "credits_requested": 10,
            "status": "PENDING",
            "amount_etb": 100.0,
            "payment_method": "Bank Account (CBE)",
        }

        update, context = self._create_mock_update_context()
        context.user_data["state"] = ConversationState.WAITING_FOR_PAYMENT_SCREENSHOT.name
        context.user_data["selected_package"] = "credits_10"
        context.user_data["payment_method"] = "Bank Account (CBE)"

        # Mock photo
        mock_photo = MagicMock()
        mock_photo.file_id = "test_file_id_123"
        update.effective_message.photo = [mock_photo]

        await payment_screenshot_handler(update, context)

        mock_create_payment.assert_called_once()
        self.assertEqual(context.user_data.get("state"), ConversationState.IDLE.name)
        self.assertNotIn("selected_package", context.user_data)
        self.assertNotIn("payment_method", context.user_data)
        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("Payment Receipt Submitted", args[0])
        self.assertIn("pay_mock123", args[0])

    @patch("handlers.credits.payment_service.create_payment_request")
    async def test_photo_sent_in_idle_does_not_create_payment(self, mock_create_payment):
        """Verify sending a photo in IDLE state does NOT create a payment record."""
        from handlers.credits import payment_screenshot_handler
        update, context = self._create_mock_update_context()
        context.user_data["state"] = ConversationState.IDLE.name

        mock_photo = MagicMock()
        mock_photo.file_id = "test_file_id_random"
        update.effective_message.photo = [mock_photo]

        await payment_screenshot_handler(update, context)

        mock_create_payment.assert_not_called()
        update.effective_message.reply_text.assert_called_once()
        args, _ = update.effective_message.reply_text.call_args
        self.assertIn("🛒 Buy Credits", args[0])

    @patch("handlers.upload.credit_service.get_authoritative_balance", return_value=(True, 3, None))
    @patch("handlers.upload.user_service.get_or_create_user")
    async def test_upload_init_with_credits(self, mock_user, mock_balance):
        """Verify Upload button transitions to WAITING_FOR_PDF when user has balance."""
        from handlers.upload import upload_init_handler
        update, context = self._create_mock_update_context()

        await upload_init_handler(update, context)

        self.assertEqual(context.user_data.get("state"), ConversationState.WAITING_FOR_PDF.name)
        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("Please send your Fayda ID PDF", args[0])

    @patch("handlers.upload.credit_service.get_authoritative_balance", return_value=(True, 0, None))
    @patch("handlers.upload.user_service.get_or_create_user")
    async def test_upload_init_zero_credits_prompts_buy_credits(self, mock_user, mock_balance):
        """Verify Upload button prompts user to buy credits when balance is 0."""
        from handlers.upload import upload_init_handler
        update, context = self._create_mock_update_context()

        await upload_init_handler(update, context)

        self.assertEqual(context.user_data.get("state"), ConversationState.IDLE.name)
        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("don't have enough credits", args[0])
        self.assertIn("🛒 Buy Credits", args[0])

    async def test_cancel_handler_resets_state_and_shows_main_menu(self):
        """Verify Cancel handler cleanly resets state and displays main menu."""
        from handlers.upload import cancel_handler
        update, context = self._create_mock_update_context()
        context.user_data["state"] = ConversationState.WAITING_FOR_PACKAGE_SELECTION.name
        context.user_data["selected_package"] = "credits_50"

        await cancel_handler(update, context)

        self.assertEqual(context.user_data.get("state"), ConversationState.IDLE.name)
        self.assertNotIn("selected_package", context.user_data)
        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("Operation cancelled", args[0])
        kb = kwargs["reply_markup"]
        btn_texts = [btn.text for row in kb.keyboard for btn in row]
        self.assertIn("📸 Upload / Process ID", btn_texts)

    @patch("handlers.jobs.job_service.get_user_jobs")
    async def test_my_jobs_handler(self, mock_jobs):
        """Verify My Jobs displays job history and main menu keyboard."""
        from handlers.jobs import jobs_handler
        mock_jobs.return_value = [
            {"id": "job_1", "status": "COMPLETED", "created_at": "2026-10-10 05:00:00"}
        ]
        update, context = self._create_mock_update_context()

        await jobs_handler(update, context)

        self.assertEqual(context.user_data.get("state"), ConversationState.IDLE.name)
        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("job_1", args[0])
        self.assertIn("COMPLETED", args[0])

    @patch("handlers.credits.settings")
    async def test_unauthorized_user_blocked_from_admin_callbacks(self, mock_settings):
        """Verify unauthorized users cannot execute administrative callbacks."""
        from handlers.credits import admin_payment_callback_handler
        mock_settings.ADMIN_TELEGRAM_IDS = (7246416805,)

        update = MagicMock()
        update.effective_user.id = 999999999  # Not an admin
        update.callback_query.data = "approve_payment:pay_123"
        update.callback_query.answer = AsyncMock()
        context = MagicMock()

        await admin_payment_callback_handler(update, context)

        update.callback_query.answer.assert_called_once()
        args, kwargs = update.callback_query.answer.call_args
        self.assertIn("Unauthorized", args[0])


if __name__ == "__main__":
    unittest.main()
