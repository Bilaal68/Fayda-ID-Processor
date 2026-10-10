"""
Payment Top-Up Verification and Approval Handlers.

Allows administrators to review pending payment receipts, view receipt images,
and atomically approve or reject top-up submissions with audit trails.
"""

import html
import io
from typing import List, Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.authorization import admin_only, check_rate_limit
from services.backend_client import backend_client
from config import settings, setup_logger

logger = setup_logger("payments_handler")


def format_payment_summary(p: Dict[str, Any]) -> str:
    """Format single payment record summary."""
    pid = p.get("id", "N/A")
    tg_id = p.get("telegram_user_id") or "N/A"
    tg_uname = f"@{p['telegram_username']}" if p.get("telegram_username") else "None"
    amount = p.get("amount_etb", 0)
    credits = p.get("credits_requested", 0)
    method = p.get("payment_method", "Bank Transfer")
    status = p.get("status", "PENDING").upper()
    created = str(p.get("created_at", ""))[:19]

    status_icon = "⏳" if status == "PENDING" else ("✅" if status == "APPROVED" else "❌")

    return (
        f"🧾 <b>Payment Ref:</b> <code>{pid}</code>\n"
        f"• <b>Status:</b> {status_icon} <b>{status}</b>\n"
        f"• <b>Telegram User:</b> <code>{tg_id}</code> ({html.escape(str(tg_uname))})\n"
        f"• <b>Amount:</b> <b>{amount:,.2f} ETB</b>\n"
        f"• <b>Requested Credits:</b> <b>+{credits} credits</b>\n"
        f"• <b>Method:</b> {html.escape(str(method))}\n"
        f"• <b>Submitted:</b> {created}\n"
    )


@admin_only
async def callback_list_payments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    List payments paginated.
    Callback data: 'nav:payments:{PENDING|ALL}:{offset}'
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = (query.data or "").split(":")
    status_filter = parts[2] if len(parts) > 2 else "PENDING"
    offset = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    limit = settings.PAGE_SIZE

    api_status = None if status_filter == "ALL" else "PENDING"

    ok, data, err = await backend_client.list_payments(status=api_status, limit=limit, offset=offset)
    if not ok:
        await query.edit_message_text(
            text=f"⚠️ <b>Failed to load payments</b>\n\n<code>{html.escape(err or 'Backend error')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]]),
            parse_mode="HTML"
        )
        return

    payments = data.get("payments", [])
    total = data.get("total", 0)
    counts = data.get("counts", {})
    pending_count = counts.get("pending", 0)

    title = "⏳ <b>Pending Payment Requests</b>" if status_filter == "PENDING" else "📜 <b>All Payment Records</b>"

    if not payments:
        empty_text = (
            f"{title}\n\n"
            f"No payments found in this category.\n"
            f"<i>Pending in system: {pending_count}</i>"
        )
        keyboard = [
            [
                InlineKeyboardButton("⏳ View Pending", callback_data="nav:payments:PENDING:0") if status_filter == "ALL"
                else InlineKeyboardButton("📜 View All History", callback_data="nav:payments:ALL:0")
            ],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]
        ]
        await query.edit_message_text(text=empty_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return

    page_num = (offset // limit) + 1
    total_pages = max(1, (total + limit - 1) // limit)

    msg_lines = [
        f"{title} (Page {page_num}/{total_pages})\n"
        f"<i>Total matching: {total} | Unreviewed Pending: {pending_count}</i>\n"
    ]

    keyboard: List[List[InlineKeyboardButton]] = []
    for p in payments:
        pid = p["id"]
        amt = p.get("amount_etb", 0)
        creds = p.get("credits_requested", 0)
        p_status = p.get("status", "PENDING")
        icon = "⏳" if p_status == "PENDING" else ("✅" if p_status == "APPROVED" else "❌")

        button_label = f"{icon} {pid[:12]} | {amt:,.0f} ETB (+{creds}c)"
        keyboard.append([InlineKeyboardButton(button_label, callback_data=f"pay:view:{pid}")])

    # Pagination navigation
    nav_row: List[InlineKeyboardButton] = []
    if offset > 0:
        prev_off = max(0, offset - limit)
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"nav:payments:{status_filter}:{prev_off}"))

    nav_row.append(InlineKeyboardButton(f"📄 {page_num}/{total_pages}", callback_data="noop"))

    if offset + limit < total:
        next_off = offset + limit
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"nav:payments:{status_filter}:{next_off}"))

    if nav_row:
        keyboard.append(nav_row)

    # Filter toggles & Menu
    filter_toggle = (
        InlineKeyboardButton("📜 View All History", callback_data="nav:payments:ALL:0")
        if status_filter == "PENDING"
        else InlineKeyboardButton("⏳ View Pending Only", callback_data="nav:payments:PENDING:0")
    )
    keyboard.append([filter_toggle, InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")])

    await query.edit_message_text(
        text="\n".join(msg_lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


@admin_only
async def callback_view_payment_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inspect full details of a payment request."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = (query.data or "").split(":")
    if len(parts) < 3:
        return
    payment_id = parts[2]

    ok, data, err = await backend_client.get_payment_detail(payment_id)
    if not ok or not data:
        await query.edit_message_text(
            text=f"⚠️ Payment not found:\n<code>{html.escape(err or 'Not found')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Payments", callback_data="nav:payments:PENDING:0")]]),
            parse_mode="HTML"
        )
        return

    payment = data.get("data") if "data" in data else data
    user_balance = data.get("user_balance")

    status = payment.get("status", "PENDING").upper()
    rejection_reason = payment.get("rejection_reason")
    has_receipt = bool(payment.get("screenshot_file_id") or payment.get("screenshot_url"))

    text = format_payment_summary(payment)
    if user_balance is not None:
        text += f"• <b>User's Current Credit Balance:</b> <code>{user_balance}</code> credits\n"

    if status == "REJECTED" and rejection_reason:
        text += f"\n❌ <b>Rejection Reason:</b> <i>{html.escape(str(rejection_reason))}</i>\n"
    elif status == "APPROVED":
        reviewer = payment.get("reviewed_by_email") or f"Admin #{payment.get('reviewed_by')}"
        text += f"\n✅ <b>Approved by:</b> {html.escape(str(reviewer))} at {payment.get('reviewed_at')}\n"

    keyboard: List[List[InlineKeyboardButton]] = []

    # View receipt button if available
    if has_receipt:
        keyboard.append([InlineKeyboardButton("🖼️ View Receipt Image", callback_data=f"pay:receipt:{payment_id}")])

    # Action buttons only if PENDING
    if status == "PENDING":
        keyboard.append([
            InlineKeyboardButton("✅ APPROVE (+Credits)", callback_data=f"pay:approve_confirm:{payment_id}"),
            InlineKeyboardButton("❌ REJECT", callback_data=f"pay:reject_prompt:{payment_id}")
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ Back to Payments", callback_data="nav:payments:PENDING:0"),
        InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")
    ])

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


@admin_only
async def callback_view_receipt_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download receipt bytes from backend and display to administrator."""
    query = update.callback_query
    if not query:
        return
    await query.answer("Fetching receipt image from storage...")

    parts = (query.data or "").split(":")
    if len(parts) < 3:
        return
    payment_id = parts[2]

    ok, img_bytes, ctype, err = await backend_client.get_payment_receipt_bytes(payment_id)
    if not ok or not img_bytes:
        await query.answer(f"Failed to fetch receipt: {err}", show_alert=True)
        return

    # Send receipt photo directly to the admin
    bio = io.BytesIO(img_bytes)
    bio.name = f"receipt_{payment_id}.jpg"
    bio.seek(0)

    caption = f"🧾 <b>Receipt for Payment:</b> <code>{payment_id}</code>"
    keyboard = [[InlineKeyboardButton("⬅️ Back to Payment Details", callback_data=f"pay:view:{payment_id}")]]

    if update.effective_chat:
        await update.effective_chat.send_photo(
            photo=bio,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )


@admin_only
async def callback_approve_confirm_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show explicit confirmation dialog before approving payment and adding credits."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = (query.data or "").split(":")
    if len(parts) < 3:
        return
    payment_id = parts[2]

    ok, data, err = await backend_client.get_payment_detail(payment_id)
    if not ok or not data:
        await query.edit_message_text("Payment not found or expired.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="nav:main")]]))
        return

    payment = data.get("data") if "data" in data else data
    if payment.get("status") != "PENDING":
        await query.answer(f"Payment is already {payment.get('status')}.", show_alert=True)
        return

    amount = payment.get("amount_etb", 0)
    credits = payment.get("credits_requested", 0)
    tg_id = payment.get("telegram_user_id", "N/A")

    confirm_text = (
        f"⚠️ <b>CONFIRM PAYMENT APPROVAL</b>\n\n"
        f"• <b>Payment ID:</b> <code>{payment_id}</code>\n"
        f"• <b>Target User:</b> Telegram <code>{tg_id}</code>\n"
        f"• <b>Amount Paid:</b> <b>{amount:,.2f} ETB</b>\n"
        f"• <b>Credits to Grant:</b> <b>+{credits} credits</b>\n\n"
        f"Have you verified that these funds were actually received in your bank/Telebirr account?\n"
        f"Clicking Confirm will atomically credit the user's balance and notify them."
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ YES, Approve & Issue Credits", callback_data=f"pay:approve_do:{payment_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"pay:view:{payment_id}")
        ]
    ]

    await query.edit_message_text(text=confirm_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


@admin_only
async def callback_approve_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute payment approval via backend."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    admin_user = update.effective_user
    admin_id = admin_user.id if admin_user else 0

    if not check_rate_limit(admin_id):
        await query.answer("Please wait a moment before retrying.", show_alert=True)
        return

    parts = (query.data or "").split(":")
    if len(parts) < 3:
        return
    payment_id = parts[2]

    ok, res, err = await backend_client.approve_payment(payment_id)
    if not ok or not res:
        logger.error("Admin %s failed to approve payment %s: %s", admin_id, payment_id, err)
        await query.edit_message_text(
            text=f"❌ <b>Approval Failed</b>\n\n<code>{html.escape(err or 'Approval error')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Return to Payment", callback_data=f"pay:view:{payment_id}")]]),
            parse_mode="HTML"
        )
        return

    new_balance = res.get("new_balance", 0)
    credits_added = res.get("credits_added", 0)

    logger.info("Admin %s approved payment %s (+%d credits, new bal: %d)", admin_id, payment_id, credits_added, new_balance)

    success_text = (
        f"✅ <b>Payment Approved Successfully</b>\n\n"
        f"• <b>Payment ID:</b> <code>{payment_id}</code>\n"
        f"• <b>Credits Granted:</b> <b>+{credits_added} credits</b>\n"
        f"• <b>User New Balance:</b> <code>{new_balance}</code> credits\n\n"
        f"The transaction has been committed and an automated receipt confirmation was sent to the user."
    )

    keyboard = [
        [InlineKeyboardButton("⏳ View Remaining Pending", callback_data="nav:payments:PENDING:0")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]
    ]

    await query.edit_message_text(text=success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


@admin_only
async def callback_reject_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt administrator to provide reason for rejecting payment."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = (query.data or "").split(":")
    if len(parts) < 3:
        return
    payment_id = parts[2]

    context.user_data["payment_reject_flow"] = {
        "payment_id": payment_id
    }

    prompt_text = (
        f"❌ <b>Reject Payment Top-Up</b>\n\n"
        f"Payment ID: <code>{payment_id}</code>\n\n"
        f"Please send a message explaining the <b>rejection reason</b>:\n"
        f"<i>(e.g., 'Payment not received in account', 'Unreadable receipt screenshot', 'Duplicate submission')</i>\n\n"
        f"Or send /cancel to abort."
    )

    keyboard = [[InlineKeyboardButton("❌ Cancel Rejection", callback_data=f"pay:view:{payment_id}")]]
    await query.edit_message_text(text=prompt_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


@admin_only
async def handle_payment_rejection_reason_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive rejection reason from administrator message and execute rejection."""
    reject_flow = context.user_data.get("payment_reject_flow")
    if not reject_flow:
        return

    context.user_data.pop("payment_reject_flow", None)
    message = update.effective_message
    if not message or not message.text:
        return

    reason = message.text.strip()
    payment_id = reject_flow["payment_id"]

    ok, res, err = await backend_client.reject_payment(payment_id=payment_id, reason=reason)
    if not ok or not res:
        await message.reply_text(
            f"❌ <b>Payment Rejection Failed</b>\n\n<code>{html.escape(err or 'Error rejecting payment')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ View Payment", callback_data=f"pay:view:{payment_id}")]])
        )
        return

    success_text = (
        f"❌ <b>Payment Rejected</b>\n\n"
        f"• <b>Payment ID:</b> <code>{payment_id}</code>\n"
        f"• <b>Status:</b> <b>REJECTED</b> (0 credits issued)\n"
        f"• <b>Recorded Reason:</b> <i>{html.escape(reason)}</i>\n\n"
        f"The payment record has been marked as rejected."
    )

    keyboard = [
        [InlineKeyboardButton("⏳ View Remaining Pending", callback_data="nav:payments:PENDING:0")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]
    ]

    await message.reply_text(text=success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

