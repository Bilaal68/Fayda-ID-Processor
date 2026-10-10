"""
Jobs History Handler

Displays previous print processing jobs.
"""

from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_main_menu_keyboard
from services import job_service
from states.conversation_states import ConversationState


async def jobs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /jobs and '📋 My Jobs' button."""
    if not update.effective_user or not update.effective_message:
        return

    context.user_data["state"] = ConversationState.IDLE.name
    context.user_data.pop("selected_package", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("submitting_payment", None)

    jobs = job_service.get_user_jobs(update.effective_user.id, limit=5)
    if not jobs:
        await update.effective_message.reply_text(
            "📋 You have no processing jobs yet.\n\n"
            "Use 📸 Upload / Process ID to submit a Fayda ID PDF.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    lines = ["📋 Recent Print Jobs:\n"]
    for j in jobs:
        icon = "✅" if j["status"] == "COMPLETED" else ("⏳" if j["status"] == "PROCESSING" else "❌")
        lines.append(f"{icon} {j['id']} | {j['status']} | {j['created_at']}")

    await update.effective_message.reply_text(
        "\n".join(lines),
        reply_markup=get_main_menu_keyboard()
    )
