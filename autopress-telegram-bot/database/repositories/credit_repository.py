"""
Credit Repository

Data access layer for the central AutoPress credit ledger (credit_transactions table).
Ensures atomic transactions, idempotency, and concurrency protection across Web and Telegram.
"""

from typing import Any, Dict, List, Optional, Tuple
from database.database import db_session, db_transaction
from utils.logger import setup_logger

logger = setup_logger(__name__)


def _resolve_user_id(cursor, telegram_user_id: int) -> Optional[int]:
    """Helper to look up internal user_id from telegram_user_id."""
    cursor.execute(
        "SELECT id FROM users WHERE telegram_user_id = ? OR telegram_user_id = ?",
        (telegram_user_id, str(telegram_user_id))
    )
    row = cursor.fetchone()
    if row:
        return row["id"]
    cursor.execute("SELECT id FROM users WHERE email = ?", (f"telegram_{telegram_user_id}@autopress.bot",))
    row = cursor.fetchone()
    return row["id"] if row else None


class CreditRepository:
    """Repository handling credit balance queries and atomic ledger mutations in unified credit_transactions table."""

    @staticmethod
    def sync_balance_snapshot(telegram_user_id: int, authoritative_balance: int) -> int:
        """
        Synchronizes local SQLite ledger with authoritative balance from the backend.
        If local balance differs from authoritative balance, inserts an AUTHORITATIVE_SYNC transaction.
        """
        try:
            with db_transaction() as conn:
                cursor = conn.cursor()
                user_id = _resolve_user_id(cursor, telegram_user_id)
                if not user_id:
                    from database.repositories.user_repository import UserRepository
                    user = UserRepository.get_or_create_user(telegram_user_id=telegram_user_id)
                    user_id = user["id"]

                cursor.execute(
                    """
                    SELECT balance_after FROM credit_transactions
                    WHERE user_id = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (user_id,)
                )
                last_row = cursor.fetchone()
                current_balance = last_row["balance_after"] if last_row else 0

                delta = authoritative_balance - current_balance
                if delta != 0:
                    cursor.execute(
                        """
                        INSERT INTO credit_transactions (
                            user_id, amount, transaction_type, reason,
                            balance_after, admin_id, processing_id, payment_id
                        ) VALUES (?, ?, 'AUTHORITATIVE_SYNC', 'Synchronized from backend central ledger', ?, NULL, NULL, NULL)
                        """,
                        (user_id, delta, authoritative_balance)
                    )
                    logger.info(
                        "Synced user %s local balance snapshot: %d -> %d (delta: %+d)",
                        telegram_user_id, current_balance, authoritative_balance, delta
                    )
                return authoritative_balance
        except Exception as e:
            logger.debug("Local balance snapshot sync notice: %s", e)
            return authoritative_balance

    @staticmethod
    def get_balance(telegram_user_id: int) -> int:
        """Fetch the authoritative credit balance for a Telegram user."""
        with db_session() as conn:
            cursor = conn.cursor()
            user_id = _resolve_user_id(cursor, telegram_user_id)
            if not user_id:
                return 0
            cursor.execute(
                """
                SELECT balance_after FROM credit_transactions
                WHERE user_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (user_id,)
            )
            row = cursor.fetchone()
            return row["balance_after"] if row else 0

    @staticmethod
    def record_transaction(
        telegram_user_id: int,
        amount: int,
        transaction_type: str,
        reason: str,
        job_id: Optional[str] = None
    ) -> Tuple[bool, str, int]:
        """
        Atomically records a credit transaction with immediate row-level lock.
        Returns: (success: bool, message: str, new_balance: int)
        """
        with db_transaction() as conn:
            cursor = conn.cursor()

            # 1. Resolve unified user_id (provisioning user if not yet present)
            user_id = _resolve_user_id(cursor, telegram_user_id)
            if not user_id:
                # Provision fallback
                from database.repositories.user_repository import UserRepository
                user = UserRepository.get_or_create_user(telegram_user_id=telegram_user_id)
                user_id = user["id"]

            # 2. Fetch current balance
            cursor.execute(
                """
                SELECT balance_after FROM credit_transactions
                WHERE user_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (user_id,)
            )
            last_row = cursor.fetchone()
            current_balance = last_row["balance_after"] if last_row else 0

            new_balance = current_balance + amount

            # Prevent negative balance
            if new_balance < 0:
                logger.warning(
                    "Credit deduction rejected: user %s has %s credits, attempted delta %s",
                    telegram_user_id, current_balance, amount
                )
                return False, f"Insufficient credits. Current balance: {current_balance}, required: {abs(amount)}", current_balance

            # 3. Check for duplicate deduction if job_id provided
            if job_id and amount < 0:
                cursor.execute(
                    """
                    SELECT id FROM credit_transactions
                    WHERE user_id = ? AND job_id = ? AND amount < 0
                    """,
                    (user_id, job_id)
                )
                if cursor.fetchone():
                    logger.info("Idempotency guard: Job %s already deducted for user %s", job_id, telegram_user_id)
                    return True, "Already deducted (idempotent)", current_balance

            # 4. Insert transaction entry
            cursor.execute(
                """
                INSERT INTO credit_transactions (
                    user_id, amount, transaction_type, reason, balance_after, job_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, amount, transaction_type, reason, new_balance, job_id)
            )

            logger.info(
                "Recorded credit transaction: User %s (ID: %s) | Delta: %+d | New Balance: %d | Type: %s | Reason: %s",
                telegram_user_id, user_id, amount, new_balance, transaction_type, reason
            )
            return True, "Success", new_balance

    @staticmethod
    def get_history(
        telegram_user_id: int,
        limit: int = 10,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        with db_session() as conn:
            cursor = conn.cursor()
            user_id = _resolve_user_id(cursor, telegram_user_id)
            if not user_id:
                return []
            cursor.execute(
                """
                SELECT * FROM credit_transactions
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset)
            )
            return [dict(r) for r in cursor.fetchall()]
