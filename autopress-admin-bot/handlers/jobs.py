"""
Processing Jobs Audit Handlers.

Displays paginated document processing jobs submitted by Telegram bot users,
allowing administrators to audit completed and failed executions.
"""

import html
from typing import List, Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.authorization import admin_only
from services.backend_client import backend_client
from config import settings, setup_logger

logger = setup_logger("jobs_handler")


def format_job_item(j: Dict[str, Any]) -> str:
    """Format single Fayda processing job record."""
    job_id = j.get("id", "N/A")
    req_id = j.get("request_id") or f"job_{job_id}"
    user_id = j.get("user_id", "N/A")
    user_name = j.get("user_name") or j.get("user_email") or f"User #{user_id}"
    count = j.get("document_count", 1)
    cost = j.get("credit_cost", 1)
    status = j.get("status", "pending").upper()
    reason = j.get("failure_reason")
    created = str(j.get("created_at", ""))[:16]

    icon = "✅" if status == "COMPLETED" else ("❌" if status == "FAILED" else "⏳")

    item_text = (
        f"{icon} <b>Job #{job_id}</b> (<code>{req_id}</code>)\n"
        f"• <b>User:</b> {html.escape(str(user_name))} (ID: <code>{user_id}</code>)\n"
        f"• <b>Cards:</b> {count} ID(s) | <b>Cost:</b> {cost} credit(s)\n"
        f"• <b>Status:</b> <code>{status}</code>\n"
        f"• <b>Date:</b> {created}\n"
    )
    if status == "FAILED" and reason:
        item_text += f"• <b>Error:</b> <i>{html.escape(str(reason))}</i>\n"

    return item_text


@admin_only
async def callback_list_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Render paginated Fayda ID processing jobs.
    Callback data: 'nav:jobs:{offset}' or 'user:jobs:{user_id}:{offset}'
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = (query.data or "").split(":")
    is_user_specific = (parts[0] == "user" and parts[1] == "jobs")

    if is_user_specific:
        user_id: Optional[int] = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        offset = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    else:
        user_id = None
        offset = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    limit = settings.PAGE_SIZE

    ok, data, err = await backend_client.get_processing_history(user_id=user_id, limit=limit, offset=offset)
    if not ok:
        await query.edit_message_text(
            text=f"⚠️ Failed to load processing jobs:\n<code>{html.escape(err or 'Error')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]]),
            parse_mode="HTML"
        )
        return

    history = data.get("history", [])
    total = data.get("total", 0)

    title = f"🖨️ <b>User #{user_id} Processing Jobs</b>" if user_id else "🖨️ <b>Fayda ID Processing Audit Log</b>"

    if not history:
        await query.edit_message_text(
            text=f"{title}\n\nNo processing records found.",
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
        f"<i>Total Processed Batches: {total}</i>\n"
    ]

    for j in history:
        msg_lines.append(format_job_item(j))

    keyboard: List[List[InlineKeyboardButton]] = []
    nav_row: List[InlineKeyboardButton] = []

    prefix = f"user:jobs:{user_id}" if user_id else "nav:jobs"

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

    await query.edit_message_text(
        text="\n".join(msg_lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

