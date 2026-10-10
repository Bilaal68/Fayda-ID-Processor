"""
Transaction History Handlers.

Displays paginated credit ledger transactions from the backend audit trail,
with support for viewing user-specific or global history.
"""

import html
from typing import List, Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from services.authorization import admin_only
from services.backend_client import backend_client
from config import settings, setup_logger

logger = setup_logger("transactions_handler")


def format_transaction_item(tx: Dict[str, Any]) -> str:
    """Format single transaction ledger entry."""
    tx_id = tx.get("id", "N/A")
    user_id = tx.get("user_id", "N/A")
    user_name = tx.get("user_name") or tx.get("user_email") or f"User #{user_id}"
    amount = tx.get("amount", 0)
    tx_type = tx.get("transaction_type", "TX")
    reason = tx.get("reason", "Adjustment")
    balance_after = tx.get("balance_after", 0)
    created = str(tx.get("created_at", ""))[:16]

    sign = "+" if amount > 0 else ""
    icon = "➕" if amount > 0 else "➖"

    return (
        f"{icon} <b>TX #{tx_id}</b> | <b>{sign}{amount} credits</b>\n"
        f"• <b>User:</b> {html.escape(str(user_name))} (ID: <code>{user_id}</code>)\n"
        f"• <b>Type:</b> <code>{tx_type}</code>\n"
        f"• <b>Balance After:</b> <code>{balance_after}</code> credits\n"
        f"• <b>Reason:</b> <i>{html.escape(str(reason))}</i>\n"
        f"• <b>Date:</b> {created}\n"
    )


@admin_only
async def callback_list_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Render paginated transaction ledger.
    Callback data: 'nav:transactions:{offset}' or 'user:tx:{user_id}:{offset}'
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = (query.data or "").split(":")
    is_user_specific = (parts[0] == "user" and parts[1] == "tx")

    if is_user_specific:
        user_id: Optional[int] = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        offset = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    else:
        user_id = None
        offset = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    limit = settings.PAGE_SIZE

    ok, data, err = await backend_client.get_credit_history(user_id=user_id, limit=limit, offset=offset)
    if not ok:
        await query.edit_message_text(
            text=f"⚠️ Failed to load transactions:\n<code>{html.escape(err or 'Error')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]]),
            parse_mode="HTML"
        )
        return

    history = data.get("history", [])
    total = data.get("total", 0)

    title = f"📊 <b>User #{user_id} Transaction Ledger</b>" if user_id else "📊 <b>Global Credit Transaction Ledger</b>"

    if not history:
        await query.edit_message_text(
            text=f"{title}\n\nNo ledger transactions found.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to User", callback_data=f"user:view:{user_id}")] if user_id
                else [InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]
            ]),
            parse_mode="HTML"
        )
        return

    page_num = (offset // limit) + 1
    total_pages = max(1, (total + limit - 1) // limit)

    msg_lines = [
        f"{title} (Page {page_num}/{total_pages})\n"
        f"<i>Total Ledger Transactions: {total}</i>\n"
    ]

    for tx in history:
        msg_lines.append(format_transaction_item(tx))

    keyboard: List[List[InlineKeyboardButton]] = []
    nav_row: List[InlineKeyboardButton] = []

    prefix = f"user:tx:{user_id}" if user_id else "nav:transactions"

    if offset > 0:
        prev_off = max(0, offset - limit)
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{prefix}:{prev_off}"))

    nav_row.append(InlineKeyboardButton(f"📄 {page_num}/{total_pages}", callback_data="noop"))

    if offset + limit < total:
        next_off = offset + limit
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"{prefix}:{next_off}"))

    if nav_row:
        keyboard.append(nav_row)

    if user_id:
        keyboard.append([
            InlineKeyboardButton("⬅️ Back to User Profile", callback_data=f"user:view:{user_id}"),
            InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")
        ])
    else:
        keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")])

    try:
        await query.edit_message_text(
            text="\n".join(msg_lines),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            logger.debug("callback_list_transactions: message is not modified; harmless no-op.")
            return
        raise

