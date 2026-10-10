"""
Statistics and Overview Dashboard Handlers.

Displays backend-derived system statistics, distinguishing between financial revenue
in ETB and operational credit volumes.
"""

import html
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.authorization import admin_only
from services.backend_client import backend_client
from config import setup_logger

logger = setup_logger("statistics_handler")


@admin_only
async def callback_view_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render comprehensive system statistics."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    ok, stats, err = await backend_client.get_stats()
    if not ok or not stats:
        await query.edit_message_text(
            text=f"⚠️ Failed to retrieve system statistics:\n<code>{html.escape(err or 'Backend unavailable')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]]),
            parse_mode="HTML"
        )
        return

    # Extract metrics safely
    tg_users = stats.get("telegram_users", 0)
    all_users = stats.get("total_users", 0)
    active_users = stats.get("active_users", 0)
    suspended_users = stats.get("suspended_users", 0)
    new_users = stats.get("new_users_30d", 0)

    # Financial top-up metrics (ETB currency)
    total_rev_etb = stats.get("total_revenue_etb", 0.0)
    pending_payments = stats.get("pending_payments", 0)
    approved_payments = stats.get("approved_payments", 0)
    rejected_payments = stats.get("rejected_payments", 0)
    total_payments = stats.get("total_payments", 0)

    # Operational credit metrics (Quantity of processing units)
    credits_in_system = stats.get("total_credits_in_system", 0)
    credits_granted = stats.get("total_credits_granted", 0)
    credits_used = stats.get("total_credits_used", 0)

    # Processing job metrics
    total_docs = stats.get("total_documents_processed", 0)
    succ_docs = stats.get("successful_documents", 0)
    failed_docs = stats.get("failed_documents", 0)
    succ_rate = stats.get("success_rate", 100.0)

    stats_text = (
        "📈 <b>AutoPress System Statistics</b>\n\n"
        "👥 <b>Telegram Bot Users:</b>\n"
        f"• Total Registered via Bot: <b>{tg_users}</b>\n"
        f"• Platform Total (All Sources): {all_users}\n"
        f"• Active: 🟢 {active_users} | Suspended: 🔴 {suspended_users}\n"
        f"• New Registrations (Last 30 Days): <b>+{new_users}</b>\n\n"
        "💰 <b>Financial Top-Ups (ETB):</b>\n"
        f"• <b>Total Confirmed Revenue:</b> <b>{total_rev_etb:,.2f} ETB</b>\n"
        f"• Pending Requests: ⏳ <b>{pending_payments}</b>\n"
        f"• Approved Requests: ✅ {approved_payments}\n"
        f"• Rejected Requests: ❌ {rejected_payments}\n"
        f"• Total Submissions: {total_payments}\n\n"
        "💳 <b>Operational Credits Ledger:</b>\n"
        f"• Circulating User Balance: <b>{credits_in_system:,} credits</b>\n"
        f"• Total Credits Granted: +{credits_granted:,} credits\n"
        f"• Total Credits Consumed: -{credits_used:,} credits\n\n"
        "🖨️ <b>Fayda ID Print Pipeline:</b>\n"
        f"• Total Batches Processed: <b>{total_docs:,}</b>\n"
        f"• Successful Print Sheets: <b>{succ_docs:,}</b>\n"
        f"• Failed Jobs: {failed_docs}\n"
        f"• Success Rate: <b>{succ_rate}%</b>"
    )

    keyboard = [
        [
            InlineKeyboardButton("⏳ Review Pending Payments", callback_data="nav:payments:PENDING:0"),
            InlineKeyboardButton("🔄 Refresh Stats", callback_data="nav:stats")
        ],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]
    ]

    await query.edit_message_text(
        text=stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

