"""
Configuration Module for AutoPress Admin Telegram Bot.

Safely loads and validates configuration from environment variables without exposing secrets.
"""

import os
import sys
import logging
from dataclasses import dataclass, field
from typing import Tuple, Optional
from dotenv import load_dotenv

# Load variables from .env file if available
load_dotenv()


def _parse_admin_ids() -> Tuple[int, ...]:
    """
    Parse administrator numeric Telegram IDs from environment.
    Supports either ADMIN_TELEGRAM_IDS (comma-separated) or ADMIN_TELEGRAM_ID (single).
    """
    raw = os.getenv("ADMIN_TELEGRAM_IDS", "") or os.getenv("ADMIN_TELEGRAM_ID", "")
    admin_ids = []
    for item in raw.split(","):
        clean = item.strip()
        if clean.isdigit():
            admin_ids.append(int(clean))
    return tuple(admin_ids)


@dataclass
class Settings:
    """Application settings container."""

    # Telegram Bot Token for administrative bot
    ADMIN_BOT_TOKEN: str = field(default_factory=lambda: os.getenv("ADMIN_BOT_TOKEN", "").strip())

    # Authorized Administrator Numeric Telegram User IDs
    ADMIN_TELEGRAM_IDS: Tuple[int, ...] = field(default_factory=_parse_admin_ids)

    # AutoPress Flask Backend API Base URL
    BACKEND_BASE_URL: str = field(
        default_factory=lambda: os.getenv("BACKEND_BASE_URL", "http://localhost:5000").rstrip("/")
    )

    # Dedicated Telegram Admin Bot Secret
    AUTOPRESS_ADMIN_BOT_SECRET: str = field(
        default_factory=lambda: (
            os.getenv("AUTOPRESS_ADMIN_BOT_SECRET", "") or
            os.getenv("BACKEND_SERVICE_TOKEN", "")
        ).strip()
    )

    # Legacy Service-to-service token if directly provided
    BACKEND_SERVICE_TOKEN: str = field(
        default_factory=lambda: os.getenv("BACKEND_SERVICE_TOKEN", "").strip()
    )

    # Administrator credentials for backend authentication
    ADMIN_EMAIL: str = field(
        default_factory=lambda: os.getenv("ADMIN_EMAIL", "bilaalm68@gmail.com").strip().lower()
    )
    ADMIN_PASSWORD: str = field(
        default_factory=lambda: os.getenv("ADMIN_PASSWORD", "Admin123456!").strip()
    )

    # Pagination page size for Telegram inline menus
    PAGE_SIZE: int = int(os.getenv("PAGE_SIZE", "6"))

    # Logging Level
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    def validate(self) -> None:
        """Validate critical configuration settings at startup."""
        errors = []
        if not self.ADMIN_BOT_TOKEN:
            errors.append("ADMIN_BOT_TOKEN is required. Set it in your .env file.")

        if not self.ADMIN_TELEGRAM_IDS:
            errors.append(
                "ADMIN_TELEGRAM_IDS (or ADMIN_TELEGRAM_ID) must contain at least one numeric Telegram user ID."
            )

        if not self.BACKEND_BASE_URL.startswith(("http://", "https://")):
            errors.append(f"BACKEND_BASE_URL must begin with http:// or https://: '{self.BACKEND_BASE_URL}'")

        if errors:
            print("❌ Configuration Error:")
            for err in errors:
                print(f"  • {err}")
            sys.exit(1)


# Singleton settings instance
settings = Settings()


def setup_logger(name: str = "autopress_admin_bot") -> logging.Logger:
    """Configure structured logging without leaking sensitive values."""
    logger = logging.getLogger(name)
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
