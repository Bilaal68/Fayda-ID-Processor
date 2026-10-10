"""
Telegram Users Management Handlers.

Displays paginated lists, user details, and provides search functionality
restricted to Telegram-originated accounts.
"""

import html
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from services.authorization import admin_only
from services.backend_client import backend_client
from config import settings, setup_logger

logger = setup_logger("users_handler")


def format_user_card(u: Dict[str, Any]) -> str:
    """Format single user details safely in HTML."""
    uid = u.get("id", "N/A")
    tg_id = u.get("telegram_user_id") or "N/A"
    uname = f"@{u['telegram_username']}" if u.get("telegram_username") else "None"
    name = u.get("full_name") or u.get("first_name") or "Telegram User"
    balance = u.get("current_credits", 0)
    status = u.get("status", "active").upper()
    status_icon = "🟢" if status == "ACTIVE" else "🔴"
    created = str(u.get("created_at", ""))[:16]
    docs = u.get("total_documents", 0)
    succ_docs = u.get("successful_documents", 0)

    safe_name = html.escape(str(name))
    safe_uname = html.escape(str(uname))

    return (
        f"👤 <b>{safe_name}</b> ({safe_uname})\n"
        f"• <b>Internal User ID:</b> <code>{uid}</code>\n"
        f"• <b>Telegram ID:</b> <code>{tg_id}</code>\n"
        f"• <b>Balance:</b> <code>{balance}</code> credits\n"
        f"• <b>Status:</b> {status_icon} <code>{status}</code>\n"
        f"• <b>Jobs Processed:</b> {docs} (Success: {succ_docs})\n"
        f"• <b>Registered:</b> {created}\n"
    )


@admin_only
async def callback_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback to render paginated registered Telegram users."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    # Parse offset from callback data (e.g. 'nav:users:0')
    parts = (query.data or "").split(":")
    offset = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    limit = settings.PAGE_SIZE

    ok, data, err = await backend_client.list_telegram_users(limit=limit, offset=offset)
    if not ok:
        await query.edit_message_text(
            text=f"⚠️ <b>Failed to fetch Telegram users</b>\n\n<code>{html.escape(err or 'Unknown error')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]]),
            parse_mode="HTML"
        )
        return

    users = data.get("users", [])
    total = data.get("total", 0)

    if not users:
        await query.edit_message_text(
            text="👥 <b>Registered Telegram Users</b>\n\nNo Telegram users found in the database.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]]),
            parse_mode="HTML"
        )
        return

    page_num = (offset // limit) + 1
    total_pages = max(1, (total + limit - 1) // limit)

    msg_lines = [
        f"👥 <b>Registered Telegram Users</b> (Page {page_num}/{total_pages})\n"
        f"<i>Total Telegram Users: {total}</i>\n"
    ]

    keyboard: List[List[InlineKeyboardButton]] = []

    # Render each user as a selectable button for full inspection
    for u in users:
        uid = u["id"]
        tg_id = u.get("telegram_user_id", "")
        name = u.get("full_name") or u.get("first_name") or f"User {uid}"
        uname = f"@{u['telegram_username']}" if u.get("telegram_username") else f"ID:{tg_id}"
        credits = u.get("current_credits", 0)

        button_label = f"#{uid} {name[:14]} ({credits}c)"
        keyboard.append([InlineKeyboardButton(button_label, callback_data=f"user:view:{uid}")])

    # Pagination navigation buttons
    nav_row: List[InlineKeyboardButton] = []
    if offset > 0:
        prev_offset = max(0, offset - limit)
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"nav:users:{prev_offset}"))

    nav_row.append(InlineKeyboardButton(f"📄 {page_num}/{total_pages}", callback_data="noop"))

    if offset + limit < total:
        next_offset = offset + limit
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"nav:users:{next_offset}"))

    if nav_row:
        keyboard.append(nav_row)

    # Search & Main menu row
    keyboard.append([
        InlineKeyboardButton("🔍 Search User", callback_data="nav:search"),
        InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")
    ])

    try:
        await query.edit_message_text(
            text="\n".join(msg_lines),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            logger.debug("callback_list_users: message is not modified; harmless no-op.")
            return
        raise


@admin_only
async def callback_view_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View details for a specific Telegram user."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    parts = (query.data or "").split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return
    user_id = int(parts[2])

    ok, data, err = await backend_client.get_user_detail(user_id)
    if not ok or not data:
        await query.edit_message_text(
            text=f"⚠️ <b>User Details Not Found</b>\n\n<code>{html.escape(err or 'User missing')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Users", callback_data="nav:users:0")]]),
            parse_mode="HTML"
        )
        return

    user = data.get("user", {})
    credits_info = data.get("credits", {})
    proc_info = data.get("processing", {})

    name = user.get("full_name") or user.get("first_name") or "Telegram User"
    uname = f"@{user['telegram_username']}" if user.get("telegram_username") else "None"
    tg_id = user.get("telegram_user_id") or "N/A"
    bal = credits_info.get("current_balance", 0)
    received = credits_info.get("total_received", 0)
    used = credits_info.get("total_used", 0)
    total_docs = proc_info.get("total_documents", 0)
    succ_docs = proc_info.get("successful_documents", 0)
    failed_docs = proc_info.get("failed_documents", 0)
    status = user.get("status", "active").upper()
    status_icon = "🟢" if status == "ACTIVE" else "🔴"
    created = str(user.get("created_at", ""))[:19]

    text = (
        f"👤 <b>Telegram User Profile</b>\n\n"
        f"• <b>Internal User ID:</b> <code>{user.get('id')}</code>\n"
        f"• <b>Telegram Numeric ID:</b> <code>{tg_id}</code>\n"
        f"• <b>Full Name:</b> {html.escape(str(name))}\n"
        f"• <b>Telegram Username:</b> {html.escape(str(uname))}\n"
        f"• <b>Account Status:</b> {status_icon} <code>{status}</code>\n"
        f"• <b>Registration Date:</b> {created}\n\n"
        f"💳 <b>Credit Ledger:</b>\n"
        f"• <b>Current Balance:</b> <code>{bal}</code> credits\n"
        f"• <b>Total Granted:</b> +{received} credits\n"
        f"• <b>Total Consumed:</b> -{used} credits\n\n"
        f"🖨️ <b>Processing History:</b>\n"
        f"• <b>Total Fayda ID Jobs:</b> {total_docs}\n"
        f"• <b>Completed:</b> {succ_docs} | <b>Failed:</b> {failed_docs}\n"
    )

    keyboard = [
        [
            InlineKeyboardButton("➕ Add Credits", callback_data=f"credit:action:{user_id}:add"),
            InlineKeyboardButton("➖ Deduct Credits", callback_data=f"credit:action:{user_id}:remove")
        ],
        [
            InlineKeyboardButton("📊 User Transactions", callback_data=f"user:tx:{user_id}:0"),
            InlineKeyboardButton("🖨️ User Jobs", callback_data=f"user:jobs:{user_id}:0")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Users", callback_data="nav:users:0"),
            InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")
        ]
    ]

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


@admin_only
async def callback_prompt_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt administrator to enter search query."""
    query = update.callback_query
    if query:
        await query.answer()

    context.user_data["awaiting_user_search"] = True

    prompt_text = (
        "🔍 <b>Search Telegram Users</b>\n\n"
        "Send a message containing any of the following:\n"
        "• Telegram Numeric ID (e.g. <code>1806429941</code>)\n"
        "• Username (e.g. <code>@username</code> or <code>username</code>)\n"
        "• Internal User ID (e.g. <code>85</code>)\n"
        "• First or Last Name\n\n"
        "<i>Or send /cancel to return to the main menu.</i>"
    )
    keyboard = [[InlineKeyboardButton("❌ Cancel Search", callback_data="nav:main")]]

    if query:
        await query.edit_message_text(text=prompt_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif update.effective_message:
        await update.effective_message.reply_text(text=prompt_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


@admin_only
async def handle_user_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process search input sent by administrator."""
    if not context.user_data.get("awaiting_user_search"):
        return

    context.user_data["awaiting_user_search"] = False
    message = update.effective_message
    if not message or not message.text:
        return

    search_query = message.text.strip().lstrip("@")
    if not search_query:
        await message.reply_text("Search query cannot be empty. Returning to menu.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]]))
        return

    ok, data, err = await backend_client.list_telegram_users(search=search_query, limit=10, offset=0)
    if not ok:
        await message.reply_text(
            f"⚠️ <b>Search Failed</b>\n\n<code>{html.escape(err or 'Error searching users')}</code>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]]),
            parse_mode="HTML"
        )
        return

    users = data.get("users", [])
    if not users:
        await message.reply_text(
            f"🔍 No Telegram users found matching: <code>{html.escape(search_query)}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Search Again", callback_data="nav:search")],
                [InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")]
            ]),
            parse_mode="HTML"
        )
        return

    keyboard: List[List[InlineKeyboardButton]] = []
    for u in users:
        uid = u["id"]
        tg_id = u.get("telegram_user_id", "")
        name = u.get("full_name") or u.get("first_name") or f"User {uid}"
        credits = u.get("current_credits", 0)
        keyboard.append([InlineKeyboardButton(f"#{uid} {name[:14]} (TG: {tg_id} | {credits}c)", callback_data=f"user:view:{uid}")])

    keyboard.append([
        InlineKeyboardButton("🔍 New Search", callback_data="nav:search"),
        InlineKeyboardButton("🔙 Main Menu", callback_data="nav:main")
    ])

    await message.reply_text(
        f"🔍 Found <b>{len(users)}</b> user(s) matching <code>{html.escape(search_query)}</code>:\nSelect a user to inspect:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

