"""
Language Handler

Handles switching between Amharic and English.
"""

from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_main_menu_keyboard
from services import user_service
from states.conversation_states import ConversationState


async def language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /language and '🌐 Language' button."""
    if not update.effective_user or not update.effective_message:
        return

    context.user_data["state"] = ConversationState.IDLE.name
    context.user_data.pop("selected_package", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("submitting_payment", None)

    user = user_service.get_or_create_user(
        telegram_user_id=update.effective_user.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name
    )

    current_lang = user.get("language", "am")
    new_lang = "en" if current_lang == "am" else "am"
    user_service.set_language(update.effective_user.id, new_lang)

    lang_name = "English" if new_lang == "en" else "አማርኛ (Amharic)"
    await update.effective_message.reply_text(
        f"🌐 Language updated to: {lang_name}",
        reply_markup=get_main_menu_keyboard()
    )
