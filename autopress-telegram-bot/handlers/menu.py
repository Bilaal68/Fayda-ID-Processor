"""
Main Menu Handler

Displays the primary navigation menu.
"""

from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_main_menu_keyboard
from services import credit_service
from states.conversation_states import ConversationState


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /menu command or Back to Menu button."""
    if not update.effective_user or not update.effective_message:
        return

    context.user_data["state"] = ConversationState.IDLE.name
    context.user_data.pop("selected_package", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("submitting_payment", None)
    balance = credit_service.get_balance(update.effective_user.id)

    await update.effective_message.reply_text(
        f"📋 AutoPress Main Menu\n\n"
        f"💳 Available Credits: {balance}\n\n"
        "Select an option below:",
        reply_markup=get_main_menu_keyboard()
    )
