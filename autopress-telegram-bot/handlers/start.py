"""
Start Command Handler

Handles user onboarding, profile creation, and displays the main navigation menu.
"""

from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_main_menu_keyboard
from services import user_service, credit_service
from states.conversation_states import ConversationState
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    if not update.effective_user or not update.effective_message:
        return

    user = update.effective_user
    context.user_data["state"] = ConversationState.IDLE.name
    context.user_data.pop("selected_package", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("submitting_payment", None)

    bot_user = user_service.get_or_create_user(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    balance = credit_service.get_balance(user.id)
    user_name = user.first_name or "User"

    logger.info("User %s (ID: %s) started bot. Initial balance: %d", user_name, user.id, balance)

    await update.effective_message.reply_text(
        f"👋 Welcome to AutoPress Fayda Print Automation, {user_name}!\n\n"
        f"Transform digital Fayda National ID PDFs into millimeter-accurate, 300 DPI multi-card PVC print sheets.\n\n"
        f"💳 Your Current Balance: {balance} credit{'s' if balance != 1 else ''}\n\n"
        "Select an option from the menu below to get started:",
        reply_markup=get_main_menu_keyboard()
    )
