"""
User Service

Handles user profile logic, onboarding, and language preferences.
"""

from typing import Any, Dict, Optional
from database.repositories.user_repository import UserRepository
from utils.logger import setup_logger

logger = setup_logger(__name__)


class UserService:
    """Service layer managing Telegram bot user profiles."""

    @staticmethod
    def get_or_create_user(
        telegram_user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        user = UserRepository.get_or_create_user(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language=language
        )

        # Sync with central AutoPress backend
        try:
            import threading
            import httpx
            from config import settings

            def _sync():
                try:
                    with httpx.Client(timeout=3.0) as client:
                        client.post(
                            f"{settings.AUTOPRESS_API_URL}/api/user/telegram/sync",
                            json={
                                "telegram_user_id": telegram_user_id,
                                "username": username or "",
                                "first_name": first_name or "",
                                "last_name": last_name or "",
                                "full_name": f"{first_name or ''} {last_name or ''}".strip()
                            }
                        )
                except Exception as e:
                    logger.debug("Backend user sync notice: %s", e)

            threading.Thread(target=_sync, daemon=True).start()
        except Exception as e:
            logger.debug("Could not trigger background user sync: %s", e)

        return user

    @staticmethod
    def get_user(telegram_user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve user profile by Telegram User ID."""
        return UserRepository.get_user(telegram_user_id)

    @staticmethod
    def set_language(telegram_user_id: int, language: str) -> bool:
        """Update language preference for the user."""
        return UserRepository.update_language(telegram_user_id, language)


user_service = UserService()
