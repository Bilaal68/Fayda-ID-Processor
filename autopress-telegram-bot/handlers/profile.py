"""
Profile Handler

Displays account information for the authenticated Telegram user.
"""

from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_main_menu_keyboard
from services import user_service, credit_service
from states.conversation_states import ConversationState


async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /profile and '👤 My Profile' button."""
    if not update.effective_user or not update.effective_message:
        return

    context.user_data["state"] = ConversationState.IDLE.name
    context.user_data.pop("selected_package", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("submitting_payment", None)

    user_id = update.effective_user.id
    user = user_service.get_or_create_user(
        telegram_user_id=user_id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name
    )
    balance = credit_service.get_balance(user_id)

    name = update.effective_user.full_name or "Valued User"
    username_str = f"@{update.effective_user.username}" if update.effective_user.username else "N/A"

    await update.effective_message.reply_text(
        f"👤 Account Profile\n\n"
        f"Name: {name}\n"
        f"Telegram ID: {user_id}\n"
        f"Username: {username_str}\n"
        f"Language: {user.get('language', 'am').upper()}\n"
        f"Available Credits: {balance}\n"
        f"Registered: {user.get('created_at', 'N/A')}",
        reply_markup=get_main_menu_keyboard()
    )
