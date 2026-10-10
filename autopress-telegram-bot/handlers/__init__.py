"""
AutoPress Telegram Bot - Handlers Package

Registers all Telegram commands, reply keyboard buttons, document upload,
photo receipt, and admin callback handlers.
"""

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from handlers.start import start_handler
from handlers.help import help_handler
from handlers.menu import menu_handler
from handlers.credits import (
    credits_handler,
    topup_init_handler,
    package_selected_handler,
    payment_method_selected_handler,
    payment_screenshot_handler,
    admin_payment_callback_handler,
    topup_back_handler,
    my_payments_handler,
    admin_pending_payments_handler,
)
from handlers.upload import (
    upload_init_handler,
    document_upload_handler,
    cancel_handler,
    generic_non_document_handler
)
from handlers.jobs import jobs_handler
from handlers.profile import profile_handler
from handlers.language import language_handler
from utils.logger import setup_logger

logger = setup_logger(__name__)


def register_handlers(application: Application) -> None:
    """Register all command, button, and document handlers with the Telegram application."""
    # 1. Commands
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("menu", menu_handler))
    application.add_handler(CommandHandler("credits", credits_handler))
    application.add_handler(CommandHandler("balance", credits_handler))
    application.add_handler(CommandHandler("topup", topup_init_handler))
    application.add_handler(CommandHandler("buy_credits", topup_init_handler))
    application.add_handler(CommandHandler("my_payments", my_payments_handler))
    application.add_handler(CommandHandler("payments", my_payments_handler))
    application.add_handler(CommandHandler("admin_payments", admin_pending_payments_handler))
    application.add_handler(CommandHandler("pending_payments", admin_pending_payments_handler))
    application.add_handler(CommandHandler("upload", upload_init_handler))
    application.add_handler(CommandHandler("cancel", cancel_handler))
    application.add_handler(CommandHandler("jobs", jobs_handler))
    application.add_handler(CommandHandler("profile", profile_handler))
    application.add_handler(CommandHandler("language", language_handler))

    # 2. Callback Queries (Inline button actions for admin approval / rejection)
    application.add_handler(
        CallbackQueryHandler(
            admin_payment_callback_handler,
            pattern=r"^(approve_payment|reject_payment):"
        )
    )

    # 3. Main Menu & Navigation Button Handlers (Case-insensitive regex matches)
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^(📸\s*Upload\s*(/\s*Process\s*ID)?|📤\s*Upload)$"), upload_init_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^(💳\s*Balance|💰\s*Balance)$"), credits_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^(🛒\s*Buy\s*Credits|💳\s*Top[- ]?Up(\s*Credits)?)$"), topup_init_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^💳\s*My\s*Payments?$"), my_payments_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^(📋\s*My\s*Jobs|📜\s*History)$"), jobs_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^(👤\s*My\s*Profile|👤\s*Profile)$"), profile_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^🌐\s*Language$"), language_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^(ℹ️\s*Help|❓\s*Help)$"), help_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^(🏠\s*Main\s*Menu|Main\s*Menu|Menu|🏠\s*Back\s*to\s*Menu)$"), menu_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^⬅️\s*Back$"), topup_back_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^(❌\s*Cancel|Cancel)$"), cancel_handler))

    # 4. Top-Up Package Selection Buttons (e.g., '10 Credits — 100 ETB')
    pkg_pattern = r"(?i)^\d+\s*Credits\s*—\s*[\d,]+\s*ETB$"
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(pkg_pattern), package_selected_handler))

    # 5. Payment Method Selection Buttons
    pm_pattern = r"(?i)^(🏦\s*Bank\s*Account|📱\s*Telebirr)"
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(pm_pattern), payment_method_selected_handler))

    # 6. Photos (for Payment Receipt screenshots)
    application.add_handler(MessageHandler(filters.PHOTO, payment_screenshot_handler))

    # 7. Document / Media Upload Handlers (PDFs or Image documents)
    application.add_handler(MessageHandler(filters.Document.ALL, document_upload_handler))

    # 8. Catch-all for non-document messages during conversation flows
    application.add_handler(MessageHandler(~filters.COMMAND & ~filters.Document.ALL & ~filters.PHOTO, generic_non_document_handler))

    logger.info("All Telegram handlers successfully registered.")


__all__ = [
    "register_handlers",
    "start_handler",
    "help_handler",
    "menu_handler",
    "credits_handler",
    "topup_init_handler",
    "package_selected_handler",
    "payment_method_selected_handler",
    "payment_screenshot_handler",
    "admin_payment_callback_handler",
    "topup_back_handler",
    "my_payments_handler",
    "admin_pending_payments_handler",
    "upload_init_handler",
    "document_upload_handler",
    "cancel_handler",
    "jobs_handler",
    "profile_handler",
    "language_handler",
]
