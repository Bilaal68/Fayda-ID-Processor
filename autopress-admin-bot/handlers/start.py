"""
Start, Main Menu, and Navigation Handlers.

Renders the administrative dashboard main menu, help documentation,
and handles operation cancellation.
"""

import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.authorization import admin_only
from config import setup_logger

logger = setup_logger("start_handler")


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the clean 10-item administrative main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("👥 Registered Users", callback_data="nav:users:0"),
            InlineKeyboardButton("🔍 Search User", callback_data="nav:search")
        ],
        [
            InlineKeyboardButton("💳 Manage Credits", callback_data="nav:credits:select"),
            InlineKeyboardButton("⏳ Pending Payments", callback_data="nav:payments:PENDING:0")
        ],
        [
            InlineKeyboardButton("📜 Payment History", callback_data="nav:payments:ALL:0"),
            InlineKeyboardButton("📊 Transaction History", callback_data="nav:transactions:0")
        ],
        [
            InlineKeyboardButton("🖨️ Processing Jobs", callback_data="nav:jobs:0"),
            InlineKeyboardButton("📈 Statistics", callback_data="nav:stats")
        ],
        [
            InlineKeyboardButton("🔔 Notifications", callback_data="nav:notifications"),
            InlineKeyboardButton("🔄 Refresh Menu", callback_data="nav:main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_text(admin_id: int, admin_name: str) -> str:
    """Generate professional main menu dashboard text."""
    safe_name = html.escape(admin_name)
    return (
        f"🛡️ <b>AutoPress Admin Dashboard</b>\n\n"
        f"Welcome, <b>{safe_name}</b> (<code>{admin_id}</code>)\n"
        f"Scoped exclusively to the <b>AutoPress Telegram Bot</b> platform.\n\n"
        f"Select an administration module below:"
    )


@admin_only
async def command_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command for authorized administrator."""
    # Clear any previous pending state in context
    context.user_data.clear()

    user = update.effective_user
    admin_id = user.id if user else 0
    admin_name = user.first_name if user else "Administrator"

    text = get_main_menu_text(admin_id, admin_name)
    reply_markup = get_main_menu_keyboard()

    if update.effective_message:
        await update.effective_message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )


@admin_only
async def command_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /cancel command to abort any active operation securely."""
    context.user_data.clear()
    text = (
        "🛑 <b>Operation Cancelled</b>\n\n"
        "Active session reset. Returning to the main administration menu."
    )
    user = update.effective_user
    admin_id = user.id if user else 0
    admin_name = user.first_name if user else "Administrator"

    if update.effective_message:
        await update.effective_message.reply_text(
            text=text,
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )


@admin_only
async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command providing guidance and safety requirements."""
    help_text = (
        "📖 <b>AutoPress Admin Bot — Quick Reference</b>\n\n"
        "<b>Available Commands:</b>\n"
        "• /start — Open the main administrative dashboard\n"
        "• /menu — Refresh and display the navigation menu\n"
        "• /cancel — Abort any ongoing search or credit adjustment flow\n"
        "• /help — View this guidance manual\n\n"
        "<b>Security Rules:</b>\n"
        "• All actions require explicit confirmation.\n"
        "• Credit adjustments and payment approvals are atomic and idempotent.\n"
        "• Only Telegram-originated users and records are managed here.\n"
        "• All operations are logged and synchronized with the central ledger."
    )
    if update.effective_message:
        await update.effective_message.reply_text(
            text=help_text,
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )


@admin_only
async def callback_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries returning to the main menu."""
    query = update.callback_query
    if query:
        await query.answer()
        context.user_data.clear()
        user = update.effective_user
        admin_id = user.id if user else 0
        admin_name = user.first_name if user else "Administrator"

        text = get_main_menu_text(admin_id, admin_name)
        reply_markup = get_main_menu_keyboard()

        try:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception:
            # If text is identical, ignore Telegram message not modified error
            pass

