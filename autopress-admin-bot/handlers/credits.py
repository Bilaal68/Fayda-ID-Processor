"""
Credit Balance Management Handlers.

Provides step-by-step administrator workflow for atomic credit additions
and deductions with mandatory confirmation and backend verification.
"""

import html
from typing import Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.authorization import admin_only, check_rate_limit
from services.backend_client import backend_client
from config import setup_logger

logger = setup_logger("credits_handler")


@admin_only
async def callback_credit_select_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt administrator to pick a user for credit adjustment."""
    query = update.callback_query
    if query:
        await query.answer()

    text = (
        "💳 <b>Credit Management</b>\n\n"
        "To adjust credits, first select a user:\n"
        "• Browse users via the <b>Registered Users</b> list\n"
        "• Or search directly by <b>Telegram ID / Username</b>"
    )
    keyboard = [
        [InlineKeyboardButton("👥 Browse Users", callback_data="nav:users:0")],
        [InlineKeyboardButton("🔍 Search User", callback_data="nav:search")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]
    ]
    if query:
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


@admin_only
async def callback_start_credit_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback initiated from user profile:
    data format: 'credit:action:{user_id}:{add|remove}'
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = (query.data or "").split(":")
    if len(parts) < 4:
        return

    user_id = int(parts[2])
    action = parts[3]  # 'add' or 'remove'

    # Fetch fresh balance from backend
    ok, data, err = await backend_client.get_user_detail(user_id)
    if not ok or not data:
        await query.edit_message_text(
            text=f"⚠️ Failed to retrieve target user:\n<code>{html.escape(err or 'Error')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"user:view:{user_id}")]]),
            parse_mode="HTML"
        )
        return

    user = data.get("user", {})
    credits_info = data.get("credits", {})
    current_balance = credits_info.get("current_balance", 0)
    target_name = user.get("full_name") or user.get("first_name") or f"User #{user_id}"

    # Store in context state for interactive input
    context.user_data["credit_flow"] = {
        "step": "awaiting_amount",
        "user_id": user_id,
        "target_name": target_name,
        "telegram_user_id": user.get("telegram_user_id"),
        "action": action,
        "current_balance": current_balance
    }

    action_label = "➕ ADD CREDITS" if action == "add" else "➖ DEDUCT CREDITS"
    prompt_text = (
        f"💳 <b>{action_label}</b>\n\n"
        f"Target User: <b>{html.escape(str(target_name))}</b> (ID: <code>{user_id}</code>)\n"
        f"Current Balance: <code>{current_balance}</code> credits\n\n"
        f"Please enter the <b>integer credit amount</b> to {action}:\n"
        f"<i>(Send an integer greater than 0, or /cancel to abort)</i>"
    )
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=f"user:view:{user_id}")]]

    await query.edit_message_text(text=prompt_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


@admin_only
async def handle_credit_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process credit amount and reason text inputs."""
    flow = context.user_data.get("credit_flow")
    if not flow:
        return

    message = update.effective_message
    if not message or not message.text:
        return

    user_text = message.text.strip()
    step = flow.get("step")
    user_id = flow["user_id"]
    action = flow["action"]
    current_balance = flow["current_balance"]
    target_name = flow["target_name"]

    # Step 1: Receiving Amount
    if step == "awaiting_amount":
        try:
            amount = int(user_text)
            if amount <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            await message.reply_text(
                "⚠️ <b>Invalid Amount</b>: Please enter a positive whole number greater than 0.\n"
                "<i>Or send /cancel to abort.</i>",
                parse_mode="HTML"
            )
            return

        if action == "remove" and amount > current_balance:
            await message.reply_text(
                f"⚠️ <b>Insufficient Balance</b>: User only has <code>{current_balance}</code> credits.\n"
                f"You cannot deduct <code>{amount}</code> credits (balance would become negative).\n\n"
                f"Please enter an amount up to <code>{current_balance}</code>, or send /cancel.",
                parse_mode="HTML"
            )
            return

        flow["amount"] = amount
        flow["step"] = "awaiting_reason"

        await message.reply_text(
            f"✅ Amount: <b>{amount} credits</b>\n\n"
            f"Now please provide a <b>reason / note</b> for this adjustment (audit trail):\n"
            f"<i>Example: 'Manual customer recharge', 'Issue resolution compensation', 'Admin correction'</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"user:view:{user_id}")]])
        )
        return

    # Step 2: Receiving Reason
    if step == "awaiting_reason":
        reason = user_text
        if len(reason) < 3:
            await message.reply_text("Please provide a descriptive reason (at least 3 characters).")
            return

        flow["reason"] = reason
        amount = flow["amount"]

        expected_balance = (current_balance + amount) if action == "add" else (current_balance - amount)
        flow["expected_balance"] = expected_balance
        flow["step"] = "awaiting_confirmation"

        action_symbol = "➕" if action == "add" else "➖"
        action_verb = "Addition" if action == "add" else "Deduction"

        summary_text = (
            f"⚠️ <b>CONFIRM CREDIT {action_verb.upper()}</b>\n\n"
            f"• <b>Target User:</b> {html.escape(str(target_name))} (ID: <code>{user_id}</code>)\n"
            f"• <b>Action:</b> {action_symbol} {action.upper()}\n"
            f"• <b>Adjustment Amount:</b> <b>{amount} credits</b>\n"
            f"• <b>Current Balance:</b> <code>{current_balance}</code> credits\n"
            f"• <b>Expected Resulting Balance:</b> <code>{expected_balance}</code> credits\n"
            f"• <b>Reason:</b> <i>{html.escape(reason)}</i>\n\n"
            f"<b>Do you confirm this action?</b> It will be atomically recorded in the backend ledger."
        )

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm & Apply", callback_data=f"credit:confirm:{user_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"user:view:{user_id}")
            ]
        ]

        await message.reply_text(
            text=summary_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )


@admin_only
async def callback_confirm_credit_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute confirmed credit adjustment atomically through the backend."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_user = update.effective_user
    admin_id = admin_user.id if admin_user else 0

    if not check_rate_limit(admin_id):
        await query.answer("Please wait a moment before retrying.", show_alert=True)
        return

    flow = context.user_data.get("credit_flow")
    if not flow or flow.get("step") != "awaiting_confirmation":
        await query.edit_message_text(
            "⚠️ Transaction session expired or already committed.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]])
        )
        return

    user_id = flow["user_id"]
    amount = flow["amount"]
    action = flow["action"]
    reason = flow["reason"]
    target_name = flow["target_name"]

    # Clear active session flow to prevent duplicate clicks
    context.user_data.pop("credit_flow", None)

    # Execute through central backend API
    ok, res, err = await backend_client.adjust_credits(
        user_id=user_id,
        amount=amount,
        action=action,
        reason=reason
    )

    if not ok or not res:
        logger.error("Admin %s failed to adjust credits for user %s: %s", admin_id, user_id, err)
        await query.edit_message_text(
            text=(
                f"❌ <b>Credit Adjustment Failed</b>\n\n"
                f"Backend rejected operation:\n<code>{html.escape(err or 'Unknown rejection')}</code>\n\n"
                f"No credits were modified."
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Return to User", callback_data=f"user:view:{user_id}")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]
            ]),
            parse_mode="HTML"
        )
        return

    new_balance = res.get("new_balance", res.get("balance_after", 0))
    action_symbol = "+" if action == "add" else "-"

    logger.info("Admin %s successfully executed %s %d credits for user %s (New bal: %d)", admin_id, action, amount, user_id, new_balance)

    success_text = (
        f"✅ <b>Credit Adjustment Committed</b>\n\n"
        f"• <b>Target User:</b> {html.escape(str(target_name))} (ID: <code>{user_id}</code>)\n"
        f"• <b>Delta:</b> <b>{action_symbol}{amount} credits</b>\n"
        f"• <b>Confirmed New Balance:</b> <code>{new_balance}</code> credits\n"
        f"• <b>Audit Reason:</b> <i>{html.escape(reason)}</i>\n\n"
        f"The adjustment has been saved to the central ledger and the user notified."
    )

    keyboard = [
        [InlineKeyboardButton("👤 View User Profile", callback_data=f"user:view:{user_id}")],
        [InlineKeyboardButton("📊 View Ledger Transactions", callback_data=f"user:tx:{user_id}:0")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]
    ]

    await query.edit_message_text(
        text=success_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

