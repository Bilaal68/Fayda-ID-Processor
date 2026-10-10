"""
Admin Notifications Configuration Handlers.

Provides configuration interface for administrative alerts regarding
new user registrations, incoming payment receipts, and system warnings.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.authorization import admin_only
from config import settings, setup_logger

logger = setup_logger("notifications_handler")

# In-memory settings for active admin notification subscriptions
_notification_settings = {
    "new_users": True,
    "new_payments": True,
    "system_failures": True
}


@admin_only
async def callback_view_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View and toggle administrator alert settings."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = (query.data or "").split(":")
    if len(parts) > 2:
        toggle_key = parts[2]
        if toggle_key in _notification_settings:
            _notification_settings[toggle_key] = not _notification_settings[toggle_key]

    nu_icon = "🔔 Enabled" if _notification_settings["new_users"] else "🔕 Disabled"
    np_icon = "🔔 Enabled" if _notification_settings["new_payments"] else "🔕 Disabled"
    sf_icon = "🔔 Enabled" if _notification_settings["system_failures"] else "🔕 Disabled"

    text = (
        "🔔 <b>Administrator Notification Preferences</b>\n\n"
        "Configure direct Telegram alerts sent to this admin account:\n\n"
        f"• <b>New User Registrations:</b> {nu_icon}\n"
        f"• <b>New Payment Top-Up Submissions:</b> {np_icon}\n"
        f"• <b>System Processing Failures:</b> {sf_icon}\n\n"
        "Tap a button below to toggle notifications:"
    )

    keyboard = [
        [
            InlineKeyboardButton(f"Toggle New Users ({nu_icon})", callback_data="nav:notifications:new_users")
        ],
        [
            InlineKeyboardButton(f"Toggle Payments ({np_icon})", callback_data="nav:notifications:new_payments")
        ],
        [
            InlineKeyboardButton(f"Toggle System Failures ({sf_icon})", callback_data="nav:notifications:system_failures")
        ],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]
    ]

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

