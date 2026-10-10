"""
Credits & Top-Up Payment Handlers

Handles balance checks, package selection, payment method selection,
screenshot submission, admin verification callbacks, and payment history.
"""

from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import settings, CREDIT_PACKAGES
from keyboards import (
    get_main_menu_keyboard,
    get_balance_keyboard,
    get_packages_keyboard,
    get_payment_methods_keyboard,
    get_payment_waiting_keyboard,
    get_admin_review_keyboard,
)
from services import user_service, credit_service, payment_service
from states.conversation_states import ConversationState
from utils.logger import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# 1. Balance Handler
# ---------------------------------------------------------------------------

async def credits_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /credits, /balance, and '💳 Balance' button."""
    if not update.effective_user or not update.effective_message:
        return

    user_id = update.effective_user.id
    user_service.get_or_create_user(
        telegram_user_id=user_id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name
    )

    balance = credit_service.get_balance(user_id)
    context.user_data["state"] = ConversationState.IDLE.name
    context.user_data.pop("selected_package", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("submitting_payment", None)

    if balance == 0:
        text = (
            "💳 AutoPress Balance\n\n"
            "Credits: 0\n\n"
            "Need more credits?\n"
            "Top up your balance below with 🛒 Buy Credits."
        )
    else:
        text = (
            "💳 AutoPress Balance\n\n"
            f"Credits: {balance}\n\n"
            "Need more credits?\n"
            "Top up your balance below with 🛒 Buy Credits."
        )

    await update.effective_message.reply_text(
        text,
        reply_markup=get_main_menu_keyboard()
    )


# ---------------------------------------------------------------------------
# 2. Top-Up Flow: Package Selection
# ---------------------------------------------------------------------------

async def topup_init_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /topup, /buy_credits, and '🛒 Buy Credits' button."""
    if not update.effective_user or not update.effective_message:
        return

    user_id = update.effective_user.id
    user_service.get_or_create_user(
        telegram_user_id=user_id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name
    )

    context.user_data["state"] = ConversationState.WAITING_FOR_PACKAGE_SELECTION.name
    context.user_data.pop("selected_package", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("submitting_payment", None)

    text = (
        "💳 Choose a Credit Package\n\n"
        "10 Credits — 100 ETB\n"
        "20 Credits — 200 ETB\n"
        "50 Credits — 500 ETB\n"
        "100 Credits — 1,000 ETB"
    )

    await update.effective_message.reply_text(
        text,
        reply_markup=get_packages_keyboard()
    )


async def package_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles when user selects a credit package from keyboard."""
    if not update.effective_user or not update.effective_message:
        return

    text = update.effective_message.text.strip() if update.effective_message.text else ""

    # Find matching package
    selected_pkg = None
    for pkg_id, pkg_info in CREDIT_PACKAGES.items():
        label = pkg_info.get("label", "")
        btn_text = pkg_info.get("button_text", "")
        if text.lower() in (label.lower(), btn_text.lower()):
            selected_pkg = pkg_info
            break
        if f"{pkg_info['credits']} credits" in text.lower():
            selected_pkg = pkg_info
            break

    if not selected_pkg:
        await update.effective_message.reply_text(
            "⚠️ Please select a valid package from the buttons below:",
            reply_markup=get_packages_keyboard()
        )
        return

    context.user_data["selected_package"] = selected_pkg["id"]
    context.user_data["state"] = ConversationState.WAITING_FOR_PAYMENT_METHOD.name

    logger.info("User %s selected package %s", update.effective_user.id, selected_pkg["id"])

    msg = (
        "You selected:\n\n"
        f"{selected_pkg['label']}\n\n"
        "Choose Payment Method"
    )
    await update.effective_message.reply_text(
        msg,
        reply_markup=get_payment_methods_keyboard()
    )


# ---------------------------------------------------------------------------
# 3. Top-Up Flow: Payment Method Selection
# ---------------------------------------------------------------------------

async def payment_method_selected_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles selection of Bank Account or Telebirr."""
    if not update.effective_user or not update.effective_message:
        return

    text = update.effective_message.text.strip() if update.effective_message.text else ""
    pkg_id = context.user_data.get("selected_package", "credits_10")
    package = CREDIT_PACKAGES.get(pkg_id, CREDIT_PACKAGES["credits_10"])

    is_bank = "Bank" in text or "🏦" in text or "CBE" in text.upper()
    is_telebirr = "Telebirr" in text or "📱" in text

    if not (is_bank or is_telebirr):
        await update.effective_message.reply_text(
            "⚠️ Please select a payment method from the buttons below:",
            reply_markup=get_payment_methods_keyboard()
        )
        return

    method_name = "Bank Account (CBE)" if is_bank else "Telebirr"
    context.user_data["payment_method"] = method_name
    context.user_data["state"] = ConversationState.WAITING_FOR_PAYMENT_SCREENSHOT.name

    logger.info("User %s selected payment method %s for package %s", update.effective_user.id, method_name, pkg_id)

    if is_bank:
        instructions = (
            "🏦 Bank Transfer Details\n\n"
            f"Bank: {settings.BANK_NAME}\n"
            f"Account Name: {settings.BANK_ACCOUNT_NAME}\n"
            f"Account Number: `{settings.BANK_ACCOUNT_NUMBER}`\n\n"
            f"📦 Selected Package: {package['credits']} Credits\n"
            f"💵 Amount to Pay: {package['price_etb']} ETB\n\n"
            "Instructions:\n"
            f"1. Transfer exactly {package['price_etb']} ETB to the account above.\n"
            "2. Take a screenshot of the completed transfer.\n"
            "3. Send the screenshot here as a photo or image file."
        )
    else:
        instructions = (
            "📱 Telebirr Payment Details\n\n"
            f"Method: Telebirr\n"
            f"Name: {settings.TELEBIRR_NAME}\n"
            f"Phone Number: `{settings.TELEBIRR_PHONE}`\n\n"
            f"📦 Selected Package: {package['credits']} Credits\n"
            f"💵 Amount to Pay: {package['price_etb']} ETB\n\n"
            "Instructions:\n"
            f"1. Send exactly {package['price_etb']} ETB via Telebirr to the number above.\n"
            "2. Take a screenshot of the transaction confirmation.\n"
            "3. Send the screenshot here as a photo or image file."
        )

    await update.effective_message.reply_text(
        instructions,
        parse_mode="Markdown",
        reply_markup=get_payment_waiting_keyboard()
    )


# ---------------------------------------------------------------------------
# 4. Top-Up Flow: Screenshot Receipt Submission
# ---------------------------------------------------------------------------

async def payment_screenshot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles payment screenshot photo or image document submission.
    Creates a PENDING payment record and notifies allowlisted admins.
    Validates state and guards against duplicate submissions.
    """
    if not update.effective_user or not update.effective_message:
        return

    user_id = update.effective_user.id
    current_state = context.user_data.get("state", ConversationState.IDLE.name)

    # Validate state: only accept screenshot when waiting for receipt
    if current_state not in (ConversationState.WAITING_FOR_PAYMENT_SCREENSHOT.name, ConversationState.WAITING_FOR_RECEIPT.name):
        logger.info("User %s sent photo while in state %s (not waiting for payment screenshot)", user_id, current_state)
        await update.effective_message.reply_text(
            "ℹ️ To buy credits, please tap 🛒 Buy Credits first to choose a package.\n\n"
            "To process a Fayda ID, tap 📸 Upload / Process ID and send your PDF file.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # Guard against accidental double-clicks or concurrent duplicate submissions
    if context.user_data.get("submitting_payment"):
        logger.warning("Duplicate payment submission prevented for user %s", user_id)
        return
    context.user_data["submitting_payment"] = True

    try:
        pkg_id = context.user_data.get("selected_package", "credits_10")
        package = CREDIT_PACKAGES.get(pkg_id, CREDIT_PACKAGES["credits_10"])
        payment_method = context.user_data.get("payment_method", "Bank Account (CBE)")

        # 1. Extract file_id from Photo or Image Document
        file_id = None
        if update.effective_message.photo:
            file_id = update.effective_message.photo[-1].file_id
        elif update.effective_message.document:
            doc = update.effective_message.document
            mime = (doc.mime_type or "").lower()
            fname = (doc.file_name or "").lower()
            if mime.startswith("image/") or fname.endswith((".png", ".jpg", ".jpeg", ".webp")):
                file_id = doc.file_id
            else:
                await update.effective_message.reply_text(
                    "❌ Please send a valid image file (.jpg, .png) or photo of your payment receipt.",
                    reply_markup=get_payment_waiting_keyboard()
                )
                return

        if not file_id:
            await update.effective_message.reply_text(
                "❌ No image detected. Please send a screenshot of your payment receipt.",
                reply_markup=get_payment_waiting_keyboard()
            )
            return

        # 2. Create PENDING Payment Request in Database
        payment = payment_service.create_payment_request(
            telegram_user_id=user_id,
            package_id=package["id"],
            payment_method=payment_method,
            screenshot_file_id=file_id,
            telegram_username=update.effective_user.username or ""
        )

        payment_id = payment["id"]

        # 3. Clear user topup context and return to IDLE
        context.user_data["state"] = ConversationState.IDLE.name
        context.user_data.pop("selected_package", None)
        context.user_data.pop("payment_method", None)
    finally:
        context.user_data.pop("submitting_payment", None)

    # 4. Reply to user with confirmation
    user_confirm_text = (
        "✅ Payment Receipt Submitted!\n\n"
        "Status: Pending Verification ⏳\n"
        f"Payment ID: `{payment_id}`\n"
        f"Package: {package['credits']} Credits ({package['price_etb']} ETB)\n"
        f"Method: {payment_method}\n\n"
        "Our team will verify your transaction and credit your balance shortly.\n"
        "You will receive a notification as soon as it is approved!"
    )
    await update.effective_message.reply_text(
        user_confirm_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )

    logger.info("Payment %s created by user %s. Notifying admins...", payment_id, user_id)

    # 5. Dispatch Notification to All Admins
    admin_caption = (
        "🆕 *New Top-Up Payment Request*\n\n"
        f"🆔 *Payment ID:* `{payment_id}`\n"
        f"👤 *User:* @{update.effective_user.username or 'NoUsername'} (ID: `{user_id}`)\n"
        f"📦 *Package:* {package['credits']} Credits\n"
        f"💵 *Amount:* {package['price_etb']} ETB\n"
        f"🏦 *Method:* {payment_method}\n"
        f"⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    for admin_id in settings.ADMIN_TELEGRAM_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=file_id,
                caption=admin_caption,
                parse_mode="Markdown",
                reply_markup=get_admin_review_keyboard(payment_id)
            )
            logger.info("Dispatched payment review %s to admin %s", payment_id, admin_id)
        except Exception as e:
            logger.warning("Failed to send admin notification to %s for payment %s: %s", admin_id, payment_id, e)


# ---------------------------------------------------------------------------
# 5. Admin Review Callback Handler
# ---------------------------------------------------------------------------

async def admin_payment_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles inline button clicks from admins to approve or reject payments.
    Strictly verifies admin permission and ensures idempotent approval.
    """
    query = update.callback_query
    if not query or not update.effective_user:
        return

    admin_id = update.effective_user.id
    admin_username = update.effective_user.username or f"Admin_{admin_id}"

    # 1. Strict Admin Authorization Check
    if admin_id not in settings.ADMIN_TELEGRAM_IDS:
        logger.warning("Unauthorized user %s attempted admin callback %s", admin_id, query.data)
        await query.answer("⛔ Unauthorized: You do not have admin permissions.", show_alert=True)
        return

    data = query.data or ""
    if ":" not in data:
        await query.answer("Invalid callback data", show_alert=True)
        return

    action, payment_id = data.split(":", 1)

    if action == "approve_payment":
        success, msg, payment, new_balance = payment_service.approve_payment(
            payment_id=payment_id,
            admin_id=admin_id
        )

        if not success:
            await query.answer(f"⚠️ {msg}", show_alert=True)
            return

        await query.answer("✅ Payment approved and credits added!")

        # Update admin message
        new_caption = (
            f"{query.message.caption or ''}\n\n"
            f"✅ *APPROVED* by @{admin_username} (ID: `{admin_id}`)\n"
            f"Credits granted: +{payment['credits_requested']}"
        )
        try:
            await query.edit_message_caption(
                caption=new_caption,
                parse_mode="Markdown",
                reply_markup=None  # Remove action buttons
            )
        except Exception as e:
            logger.warning("Failed to edit admin message caption: %s", e)

        # Notify User of Approval
        user_id = payment["telegram_user_id"]
        try:
            user_notify_text = (
                "🎉 *Payment Approved!*\n\n"
                f"*{payment['credits_requested']} credits* have been added to your account.\n"
                f"💰 *Current Balance:* {new_balance} credits.\n\n"
                "Thank you for using AutoPress! You can now upload and process your Fayda PDFs."
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=user_notify_text,
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard()
            )
            logger.info("Notified user %s of approved payment %s", user_id, payment_id)
        except Exception as e:
            logger.warning("Failed to notify user %s of payment approval: %s", user_id, e)

    elif action == "reject_payment":
        success, msg, payment = payment_service.reject_payment(
            payment_id=payment_id,
            admin_id=admin_id
        )

        if not success:
            await query.answer(f"⚠️ {msg}", show_alert=True)
            return

        await query.answer("❌ Payment request rejected.")

        # Update admin message
        new_caption = (
            f"{query.message.caption or ''}\n\n"
            f"❌ *REJECTED* by @{admin_username} (ID: `{admin_id}`)"
        )
        try:
            await query.edit_message_caption(
                caption=new_caption,
                parse_mode="Markdown",
                reply_markup=None  # Remove action buttons
            )
        except Exception as e:
            logger.warning("Failed to edit admin message caption: %s", e)

        # Notify User of Rejection
        user_id = payment["telegram_user_id"]
        try:
            user_notify_text = (
                "❌ *Payment Verification Notice*\n\n"
                f"Your payment receipt (`{payment_id}`) could not be verified.\n\n"
                f"If you believe this is an error, please contact support {settings.SUPPORT_CONTACT} with your transaction details."
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=user_notify_text,
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard()
            )
            logger.info("Notified user %s of rejected payment %s", user_id, payment_id)
        except Exception as e:
            logger.warning("Failed to notify user %s of payment rejection: %s", user_id, e)


# ---------------------------------------------------------------------------
# 6. Payment Back / Cancel Navigation
# ---------------------------------------------------------------------------

async def topup_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles '⬅️ Back' navigation during top-up flow."""
    if not update.effective_message:
        return

    current_state = context.user_data.get("state", ConversationState.IDLE.name)

    if current_state in (ConversationState.WAITING_FOR_PAYMENT_SCREENSHOT.name, ConversationState.WAITING_FOR_RECEIPT.name):
        context.user_data["state"] = ConversationState.WAITING_FOR_PAYMENT_METHOD.name
        pkg_id = context.user_data.get("selected_package", "credits_10")
        pkg = CREDIT_PACKAGES.get(pkg_id, CREDIT_PACKAGES["credits_10"])
        await update.effective_message.reply_text(
            f"You selected:\n\n{pkg['label']}\n\nChoose Payment Method",
            reply_markup=get_payment_methods_keyboard()
        )
    elif current_state == ConversationState.WAITING_FOR_PAYMENT_METHOD.name:
        context.user_data["state"] = ConversationState.WAITING_FOR_PACKAGE_SELECTION.name
        text = (
            "💳 Choose a Credit Package\n\n"
            "10 Credits — 100 ETB\n"
            "20 Credits — 200 ETB\n"
            "50 Credits — 500 ETB\n"
            "100 Credits — 1,000 ETB"
        )
        await update.effective_message.reply_text(
            text,
            reply_markup=get_packages_keyboard()
        )
    elif current_state == ConversationState.WAITING_FOR_PACKAGE_SELECTION.name:
        context.user_data["state"] = ConversationState.IDLE.name
        context.user_data.pop("selected_package", None)
        context.user_data.pop("payment_method", None)
        context.user_data.pop("submitting_payment", None)
        await credits_handler(update, context)
    else:
        context.user_data["state"] = ConversationState.IDLE.name
        context.user_data.pop("selected_package", None)
        context.user_data.pop("payment_method", None)
        context.user_data.pop("submitting_payment", None)
        await credits_handler(update, context)


# ---------------------------------------------------------------------------
# 7. User Payment History Handler
# ---------------------------------------------------------------------------

async def my_payments_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /my_payments and '💳 My Payments' button."""
    if not update.effective_user or not update.effective_message:
        return

    user_id = update.effective_user.id
    receipts = payment_service.get_user_payments(user_id, limit=5)

    if not receipts:
        await update.effective_message.reply_text(
            "💳 *Your Payment History*\n\n"
            "You have not submitted any payment receipts yet.\n"
            "Use *🛒 Buy Credits* to purchase credits.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
        return

    lines = ["💳 *Your Recent Payment Requests:*\n"]
    for r in receipts:
        status_icon = "⏳" if r["status"] == "PENDING" else ("✅" if r["status"] == "APPROVED" else "❌")
        pkg_credits = r.get("credits_requested", 10)
        amount = r.get("amount_etb", 100.0)
        method = r.get("payment_method", "CBE")
        created = r.get("created_at", "")
        if isinstance(created, str) and len(created) > 16:
            created = created[:16]

        lines.append(
            f"• *{pkg_credits} Credits* ({amount:.0f} ETB) — {status_icon} *{r['status']}*\n"
            f"  Method: {method} | ID: `{r['id']}`\n"
            f"  Date: {created}\n"
        )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )


# ---------------------------------------------------------------------------
# 8. Admin Pending Payments List Command
# ---------------------------------------------------------------------------

async def admin_pending_payments_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /admin_payments command for admins to inspect unreviewed requests."""
    if not update.effective_user or not update.effective_message:
        return

    user_id = update.effective_user.id
    if user_id not in settings.ADMIN_TELEGRAM_IDS:
        await update.effective_message.reply_text("⛔ Unauthorized: Admin only.")
        return

    pending = payment_service.get_pending_payments(limit=10)
    if not pending:
        await update.effective_message.reply_text("✅ No pending payment requests awaiting verification.")
        return

    await update.effective_message.reply_text(f"📋 *{len(pending)} Pending Payment Requests:*", parse_mode="Markdown")
    for p in pending:
        msg = (
            f"🆔 `{p['id']}` | User ID: `{p['telegram_user_id']}`\n"
            f"📦 {p['credits_requested']} Credits ({p['amount_etb']} ETB via {p['payment_method']})\n"
            f"⏰ {p['created_at']}"
        )
        keyboard = get_admin_review_keyboard(p["id"])
        if p.get("screenshot_file_id"):
            try:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=p["screenshot_file_id"],
                    caption=msg,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                continue
            except Exception as e:
                logger.warning("Failed to resend photo %s: %s", p.get("screenshot_file_id"), e)

        await update.effective_message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
