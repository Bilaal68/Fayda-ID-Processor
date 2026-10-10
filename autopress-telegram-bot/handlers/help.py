"""
Help Command Handler

Provides system instructions, contact info, and support channels.
"""

from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_main_menu_keyboard
from states.conversation_states import ConversationState


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /help and 'ℹ️ Help' button."""
    if not update.effective_message:
        return

    context.user_data["state"] = ConversationState.IDLE.name
    context.user_data.pop("selected_package", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("submitting_payment", None)

    await update.effective_message.reply_text(
        "ℹ️ AutoPress Help & Support\n\n"
        "How to use:\n"
        "1. Tap 📸 Upload / Process ID or send /upload\n"
        "2. Send your official Fayda National ID PDF\n"
        "3. Wait a few seconds while our engine processes OCR, photo cropping, and layout\n"
        "4. Receive your millimeter-accurate 300 DPI print-ready image\n\n"
        "💳 Need Credits?\n"
        "Tap 🛒 Buy Credits to choose a credit package and submit your payment.\n\n"
        "📞 Phone: +251978591099\n"
        "💬 Telegram: @Oronymuos\n"
        "👥 Telegram Channel: https://t.me/+El9sLg_wwF0yNzVk",
        reply_markup=get_main_menu_keyboard()
    )
