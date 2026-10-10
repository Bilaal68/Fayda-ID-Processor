"""
AutoPress Telegram Bot - Configuration Module

Loads environment variables safely without hardcoding secrets.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Tuple
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


def _parse_admin_ids() -> Tuple[int, ...]:
    """Parse comma-separated admin Telegram IDs from environment."""
    raw = os.getenv("ADMIN_TELEGRAM_IDS", "").strip()
    admin_ids = []
    if raw:
        for item in raw.split(","):
            clean = item.strip()
            if clean.isdigit():
                admin_ids.append(int(clean))
    if not admin_ids:
        import logging
        logging.getLogger(__name__).warning("ADMIN_TELEGRAM_IDS is not set or empty. No admins configured.")
    return tuple(admin_ids)


# Credit packages available for manual top-up
CREDIT_PACKAGES: Dict[str, Dict[str, Any]] = {
    "credits_10": {
        "id": "credits_10",
        "credits": 10,
        "price_etb": 100,
        "label": "10 Credits — 100 ETB",
    },
    "credits_20": {
        "id": "credits_20",
        "credits": 20,
        "price_etb": 200,
        "label": "20 Credits — 200 ETB",
    },
    "credits_50": {
        "id": "credits_50",
        "credits": 50,
        "price_etb": 500,
        "label": "50 Credits — 500 ETB",
    },
    "credits_100": {
        "id": "credits_100",
        "credits": 100,
        "price_etb": 1000,
        "label": "100 Credits — 1,000 ETB",
    },
}


@dataclass(frozen=True)
class Settings:
    """Application settings and configuration parameters."""
    
    # Telegram Bot Token
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # AutoPress Backend API Base URL
    AUTOPRESS_API_URL: str = os.getenv("AUTOPRESS_API_URL", "http://localhost:5000").rstrip("/")
    
    # JWT Secret matching backend auth service
    JWT_SECRET: str = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "autopress-jwt-secret-production-change-me"))
    
    # Service Secret for internal machine-to-machine auth
    AUTOPRESS_SERVICE_SECRET: str = os.getenv("AUTOPRESS_SERVICE_SECRET", "")
    AUTOPRESS_ADMIN_BOT_SECRET: str = os.getenv("AUTOPRESS_ADMIN_BOT_SECRET", os.getenv("AUTOPRESS_SERVICE_SECRET", ""))
    
    # Database Path / Connection (Unified AutoPress Backend Database)
    DATABASE_PATH: str = os.getenv(
        "AUTOPRESS_DB_PATH",
        os.getenv(
            "DATABASE_PATH",
            os.path.abspath(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "AutoPress-backend", "autopress.db")
            )
        )
    )
    
    # Initial welcome bonus credits for new Telegram users
    DEFAULT_SIGNUP_CREDITS: int = int(os.getenv("DEFAULT_SIGNUP_CREDITS", "2"))
    
    # Max file upload size in Megabytes
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "15"))
    
    # Localization and Default Settings
    DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "am")
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Admin & Top-Up Payment Settings
    ADMIN_TELEGRAM_IDS: Tuple[int, ...] = field(default_factory=_parse_admin_ids)
    BANK_NAME: str = os.getenv("BANK_NAME", "Commercial Bank of Ethiopia (CBE)")
    BANK_ACCOUNT_NAME: str = os.getenv("BANK_ACCOUNT_NAME", "Bilal Mohamed Hussein")
    BANK_ACCOUNT_NUMBER: str = os.getenv("BANK_ACCOUNT_NUMBER", "1000624900891")
    TELEBIRR_NAME: str = os.getenv("TELEBIRR_NAME", "Bilal Mohamed Hussein")
    TELEBIRR_PHONE: str = os.getenv("TELEBIRR_PHONE", "0978591099")
    SUPPORT_CONTACT: str = os.getenv("SUPPORT_CONTACT", "@AutoPressSupport")

    def __post_init__(self):
        if self.JWT_SECRET == "autopress-jwt-secret-production-change-me":
            import logging
            logging.getLogger(__name__).warning("Using default JWT_SECRET! Set JWT_SECRET in environment for production.")


settings = Settings()
