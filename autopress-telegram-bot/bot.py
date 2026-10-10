"""
AutoPress Telegram Bot - Entry Point

Initializes the Telegram bot application, validates configuration,
registers interaction handlers, and runs the polling event loop.
Business logic is delegated to the services package.
"""

import sys
from telegram.ext import Application, ApplicationBuilder
from telegram.request import HTTPXRequest
from config import settings
from database import init_db
from handlers import register_handlers
from utils.logger import setup_logger

logger = setup_logger(__name__)


def create_bot_app() -> Application:
    """
    Factory function to initialize and configure the Telegram bot application.
    Validates configuration and registers interaction handlers.
    """
    # 0. Initialize SQLite database schema
    init_db()

    # 1. Validate configuration & token
    token = settings.TELEGRAM_BOT_TOKEN.strip() if settings.TELEGRAM_BOT_TOKEN else ""
    if not token:
        logger.error(
            "CRITICAL: Missing TELEGRAM_BOT_TOKEN! "
            "Please configure TELEGRAM_BOT_TOKEN in your .env file or environment variables."
        )
        sys.exit(1)

    logger.info(
        "Configuration loaded successfully [Backend API: %s, Default Lang: %s]",
        settings.AUTOPRESS_API_URL,
        settings.DEFAULT_LANGUAGE,
    )

    # 2. Build Telegram Application
    try:
        request_config = HTTPXRequest(
            connect_timeout=60.0,
            read_timeout=60.0,
            write_timeout=60.0,
            pool_timeout=60.0,
        )
        application = ApplicationBuilder().token(token).request(request_config).build()
        logger.info("Telegram Application initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize Telegram Application with provided token: %s", e)
        sys.exit(1)

    # 3. Register handlers
    register_handlers(application)

    # 4. Global error handler
    async def global_error_handler(update: object, context: object) -> None:
        err = getattr(context, "error", None)
        logger.error("Telegram error caught in handler loop: %s", err)

    application.add_error_handler(global_error_handler)

    return application


def main() -> None:
    """Main execution entry point: builds application and starts polling."""
    logger.info("Starting AutoPress Telegram Bot service...")

    app = create_bot_app()

    logger.info("Starting Telegram long polling (Press Ctrl+C to stop)...")
    try:
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
            bootstrap_retries=5,
            poll_interval=0.5,
            timeout=30
        )
    except KeyboardInterrupt:
        logger.info("Bot service stopped by user.")
    except Exception as e:
        logger.error("Unexpected error during bot runtime: %s", e)
        sys.exit(1)
    finally:
        logger.info("AutoPress Telegram Bot shutdown complete.")


if __name__ == "__main__":
    main()
