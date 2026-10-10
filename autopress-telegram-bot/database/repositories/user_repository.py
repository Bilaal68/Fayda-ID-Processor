"""
User Repository

Data access layer for AutoPress users (Website, Telegram, and Linked accounts)
using the central unified AutoPress backend database.
"""

from typing import Any, Dict, Optional
from database.database import db_session, db_transaction
from config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class UserRepository:
    """Repository handling Telegram bot user identity and profile persistence in unified users table."""

    @staticmethod
    def get_user(telegram_user_id: int) -> Optional[Dict[str, Any]]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            user_dict = dict(row)
            user_dict["username"] = user_dict.get("telegram_username")
            return user_dict

    @staticmethod
    def get_or_create_user(
        telegram_user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        u_name = str(username).strip().lstrip("@") if username else ""
        f_name = str(first_name).strip() if first_name else ""
        l_name = str(last_name).strip() if last_name else ""
        default_lang = str(language) if isinstance(language, str) else settings.DEFAULT_LANGUAGE
        name_candidate = f"{f_name} {l_name}".strip() or (f"@{u_name}" if u_name else f"Telegram User {telegram_user_id}")
        is_new = False
        user_id = None

        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,)
            )
            row = cursor.fetchone()
            if row:
                user_id = row["id"]
                # Update metadata if changed and update last activity
                cursor.execute(
                    """
                    UPDATE users
                    SET telegram_username = COALESCE(NULLIF(?, ''), telegram_username),
                        first_name = COALESCE(NULLIF(?, ''), first_name),
                        last_name = COALESCE(NULLIF(?, ''), last_name),
                        full_name = CASE WHEN full_name LIKE 'Telegram User %' OR full_name LIKE '@%' THEN ? ELSE full_name END,
                        language = COALESCE(NULLIF(?, ''), language),
                        last_activity = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (u_name, f_name, l_name, name_candidate, default_lang, user_id)
                )
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                fresh_row = cursor.fetchone()
                user_dict = dict(fresh_row)
                user_dict["username"] = user_dict.get("telegram_username")
                return user_dict

            # Check by synthetic telegram email
            tg_email = f"telegram_{telegram_user_id}@autopress.bot"
            cursor.execute("SELECT * FROM users WHERE email = ?", (tg_email,))
            email_row = cursor.fetchone()
            if email_row:
                user_id = email_row["id"]
                cursor.execute(
                    """
                    UPDATE users
                    SET telegram_user_id = ?,
                        telegram_username = COALESCE(NULLIF(?, ''), telegram_username),
                        first_name = COALESCE(NULLIF(?, ''), first_name),
                        last_name = COALESCE(NULLIF(?, ''), last_name),
                        language = COALESCE(NULLIF(?, ''), language),
                        last_activity = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (telegram_user_id, u_name, f_name, l_name, default_lang, user_id)
                )
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                fresh_row = cursor.fetchone()
                user_dict = dict(fresh_row)
                user_dict["username"] = user_dict.get("telegram_username")
                return user_dict

            # Create new user record in unified users table
            cursor.execute(
                """
                INSERT INTO users (
                    email, password_hash, full_name, role, status, is_verified,
                    telegram_user_id, telegram_username, first_name, last_name, language, source
                )
                VALUES (?, '', ?, 'user', 'active', 1, ?, ?, ?, ?, ?, 'telegram')
                """,
                (tg_email, name_candidate, telegram_user_id, u_name, f_name, l_name, default_lang)
            )
            user_id = cursor.lastrowid
            is_new = True

            # Grant default signup bonus credits in credit_transactions
            if is_new and settings.DEFAULT_SIGNUP_CREDITS > 0 and user_id:
                cursor.execute(
                    """
                    INSERT INTO credit_transactions (
                        user_id, amount, transaction_type, reason, balance_after
                    ) VALUES (?, ?, 'WELCOME_BONUS', ?, ?)
                    """,
                    (
                        user_id,
                        settings.DEFAULT_SIGNUP_CREDITS,
                        f"Welcome bonus ({settings.DEFAULT_SIGNUP_CREDITS} credits)",
                        settings.DEFAULT_SIGNUP_CREDITS
                    )
                )

        logger.info("Provisioned/synced Telegram user %s (ID: %s, User ID: %s)", name_candidate, telegram_user_id, user_id)
        return {
            "id": user_id,
            "telegram_user_id": telegram_user_id,
            "username": u_name,
            "first_name": f_name,
            "last_name": l_name,
            "full_name": name_candidate,
            "language": default_lang,
            "source": "telegram"
        }

    @staticmethod
    def update_language(telegram_user_id: int, language: str) -> bool:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET language = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_user_id = ?",
                (language, telegram_user_id)
            )
            return cursor.rowcount > 0
