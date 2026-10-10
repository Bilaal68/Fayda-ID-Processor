"""
AutoPress Admin Telegram Bot - Main Application Entrypoint.

Provides a secure, production-grade Telegram administration bot for managing
Telegram bot users, credit top-up payments, balances, and Fayda processing jobs.
"""

import sys
import html
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.request import HTTPXRequest

from config import settings, setup_logger
from handlers.start import (
    command_start,
    command_cancel,
    command_help,
    callback_main_menu
)
from handlers.users import (
    callback_list_users,
    callback_view_user,
    callback_prompt_search,
    handle_user_search_input
)
from handlers.credits import (
    callback_credit_select_menu,
    callback_start_credit_action,
    callback_confirm_credit_action,
    handle_credit_text_input
)
from handlers.payments import (
    callback_list_payments,
    callback_view_payment_detail,
    callback_view_receipt_image,
    callback_approve_confirm_prompt,
    callback_approve_execute,
    callback_reject_prompt,
    handle_payment_rejection_reason_input
)
from handlers.transactions import callback_list_transactions
from handlers.jobs import callback_list_jobs
from handlers.statistics import callback_view_statistics
from handlers.notifications import callback_view_notifications

logger = setup_logger("admin_bot")


async def callback_noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle dummy informational buttons."""
    query = update.callback_query
    if query:
        await query.answer()


async def global_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route incoming text messages to appropriate active workflow based on context state."""
    # 1. User search flow
    if context.user_data.get("awaiting_user_search"):
        await handle_user_search_input(update, context)
        return

    # 2. Credit adjustment flow
    if context.user_data.get("credit_flow"):
        await handle_credit_text_input(update, context)
        return

    # 3. Payment rejection flow
    if context.user_data.get("payment_reject_flow"):
        await handle_payment_rejection_reason_input(update, context)
        return

    # Default message if no active workflow
    if update.effective_message:
        await update.effective_message.reply_text(
            "ℹ️ Please select an option from the menu or use /start.",
            parse_mode="HTML"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors safely and return understandable notifications without exposing secrets."""
    logger.error("Exception handling update: %s", context.error, exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        safe_msg = (
            "⚠️ <b>An Unexpected Error Occurred</b>\n\n"
            "The system encountered an internal issue while processing your request.\n"
            "Please try again or use /cancel to return to the main menu."
        )
        try:
            await update.effective_message.reply_text(text=safe_msg, parse_mode="HTML")
        except Exception:
            pass


async def post_init(application: Application) -> None:
    """Configure bot menu commands on startup."""
    commands = [
        BotCommand("start", "Open AutoPress admin dashboard"),
        BotCommand("menu", "Display main navigation menu"),
        BotCommand("cancel", "Abort current operation and return to menu"),
        BotCommand("help", "View administrative usage guidelines")
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Administrative bot commands configured successfully.")
    except Exception as exc:
        logger.warning("Could not set bot commands: %s", exc)


def create_admin_application() -> Application:
    """Construct and configure the Telegram application."""
    # Validate environment configuration
    settings.validate()

    request_config = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=60.0,
    )

    app = (
        Application.builder()
        .token(settings.ADMIN_BOT_TOKEN)
        .request(request_config)
        .post_init(post_init)
        .build()
    )

    # 1. Commands
    app.add_handler(CommandHandler("start", command_start))
    app.add_handler(CommandHandler("menu", command_start))
    app.add_handler(CommandHandler("cancel", command_cancel))
    app.add_handler(CommandHandler("help", command_help))

    # 2. Callbacks
    # Main menu & no-op
    app.add_handler(CallbackQueryHandler(callback_main_menu, pattern=r"^nav:main$"))
    app.add_handler(CallbackQueryHandler(callback_noop, pattern=r"^noop$"))

    # Users & Search
    app.add_handler(CallbackQueryHandler(callback_list_users, pattern=r"^nav:users:\d+$"))
    app.add_handler(CallbackQueryHandler(callback_prompt_search, pattern=r"^nav:search$"))
    app.add_handler(CallbackQueryHandler(callback_view_user, pattern=r"^user:view:\d+$"))

    # Credits
    app.add_handler(CallbackQueryHandler(callback_credit_select_menu, pattern=r"^nav:credits:select$"))
    app.add_handler(CallbackQueryHandler(callback_start_credit_action, pattern=r"^credit:action:\d+:(add|remove)$"))
    app.add_handler(CallbackQueryHandler(callback_confirm_credit_action, pattern=r"^credit:confirm:\d+$"))

    # Payments
    app.add_handler(CallbackQueryHandler(callback_list_payments, pattern=r"^nav:payments:(PENDING|ALL):\d+$"))
    app.add_handler(CallbackQueryHandler(callback_view_payment_detail, pattern=r"^pay:view:[a-zA-Z0-9_\-]+$"))
    app.add_handler(CallbackQueryHandler(callback_view_receipt_image, pattern=r"^pay:receipt:[a-zA-Z0-9_\-]+$"))
    app.add_handler(CallbackQueryHandler(callback_approve_confirm_prompt, pattern=r"^pay:approve_confirm:[a-zA-Z0-9_\-]+$"))
    app.add_handler(CallbackQueryHandler(callback_approve_execute, pattern=r"^pay:approve_do:[a-zA-Z0-9_\-]+$"))
    app.add_handler(CallbackQueryHandler(callback_reject_prompt, pattern=r"^pay:reject_prompt:[a-zA-Z0-9_\-]+$"))

    # Transactions & Jobs
    app.add_handler(CallbackQueryHandler(callback_list_transactions, pattern=r"^nav:transactions:\d+$"))
    app.add_handler(CallbackQueryHandler(callback_list_transactions, pattern=r"^user:tx:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(callback_list_jobs, pattern=r"^nav:jobs:\d+$"))
    app.add_handler(CallbackQueryHandler(callback_list_jobs, pattern=r"^user:jobs:\d+:\d+$"))

    # Statistics & Notifications
    app.add_handler(CallbackQueryHandler(callback_view_statistics, pattern=r"^nav:stats$"))
    app.add_handler(CallbackQueryHandler(callback_view_notifications, pattern=r"^nav:notifications"))

    # 3. Message handler for conversational text input
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_router))

    # 4. Error handler
    app.add_error_handler(error_handler)

    return app


def main() -> None:
    """Run the admin bot polling loop."""
    logger.info("Initializing AutoPress Admin Telegram Bot...")
    logger.info("Authorized Administrator Telegram IDs: %s", settings.ADMIN_TELEGRAM_IDS)
    logger.info("Backend API Endpoint: %s", settings.BACKEND_BASE_URL)

    app = create_admin_application()
    logger.info("Starting polling...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=5,
        poll_interval=0.5,
        timeout=30,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()

