"""
Payment Repository

Data access layer for top-up payment requests, verification, and ledger integration
in the central payment_receipts table.
Ensures atomic state transitions and idempotency for manual payment approval.
"""

from typing import Any, Dict, List, Optional, Tuple
from database.database import db_session, db_transaction
from utils.logger import setup_logger

logger = setup_logger(__name__)


def _resolve_user_id(cursor, telegram_user_id: int) -> Optional[int]:
    """Helper to look up internal user_id from telegram_user_id."""
    cursor.execute("SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,))
    row = cursor.fetchone()
    if row:
        return row["id"]
    cursor.execute("SELECT id FROM users WHERE email = ?", (f"telegram_{telegram_user_id}@autopress.bot",))
    row = cursor.fetchone()
    return row["id"] if row else None


def _resolve_admin_id(cursor, admin_id: Optional[int]) -> Optional[int]:
    """Helper to resolve admin_id to a valid users(id) foreign key reference."""
    if not admin_id:
        return None
    cursor.execute("SELECT id FROM users WHERE id = ?", (admin_id,))
    if cursor.fetchone():
        return admin_id
    cursor.execute("SELECT id FROM users WHERE telegram_user_id = ?", (admin_id,))
    row = cursor.fetchone()
    if row:
        return row["id"]
    return None


class PaymentRepository:
    """Repository handling user recharge payment receipts and admin reviews in unified payment_receipts table."""

    @staticmethod
    def create_payment_request(
        payment_id: str,
        telegram_user_id: int,
        package_id: str,
        credits_requested: int,
        amount_etb: float,
        payment_method: str,
        screenshot_file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new PENDING payment request."""
        with db_session() as conn:
            cursor = conn.cursor()
            user_id = _resolve_user_id(cursor, telegram_user_id)
            if not user_id:
                from database.repositories.user_repository import UserRepository
                user = UserRepository.get_or_create_user(telegram_user_id=telegram_user_id)
                user_id = user["id"]

            cursor.execute("SELECT telegram_username FROM users WHERE id = ?", (user_id,))
            u_row = cursor.fetchone()
            tg_uname = u_row["telegram_username"] if u_row else None

            cursor.execute(
                """
                INSERT INTO payment_receipts (
                    id, user_id, telegram_user_id, telegram_username, package_id, credits_requested,
                    amount_etb, payment_method, screenshot_file_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    payment_id,
                    user_id,
                    telegram_user_id,
                    tg_uname,
                    package_id,
                    credits_requested,
                    amount_etb,
                    payment_method,
                    screenshot_file_id
                )
            )
            logger.info(
                "Created PENDING payment request %s for user %s: %d credits (%.2f ETB via %s)",
                payment_id, telegram_user_id, credits_requested, amount_etb, payment_method
            )
            return {
                "id": payment_id,
                "user_id": user_id,
                "telegram_user_id": telegram_user_id,
                "telegram_username": tg_uname,
                "package_id": package_id,
                "credits_requested": credits_requested,
                "amount_etb": amount_etb,
                "payment_method": payment_method,
                "screenshot_file_id": screenshot_file_id,
                "status": "PENDING"
            }

    @staticmethod
    def get_payment(payment_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific payment record by ID."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM payment_receipts WHERE id = ?",
                (payment_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_user_payments(telegram_user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent payment submissions for a user."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM payment_receipts
                WHERE telegram_user_id = ?
                ORDER BY created_at DESC, rowid DESC LIMIT ?
                """,
                (telegram_user_id, limit)
            )
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def get_pending_payments(limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch unreviewed pending payments."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM payment_receipts
                WHERE status = 'PENDING'
                ORDER BY created_at ASC, rowid ASC LIMIT ?
                """,
                (limit,)
            )
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def approve_payment(
        payment_id: str,
        admin_id: int
    ) -> Tuple[bool, str, Optional[Dict[str, Any]], int]:
        """
        Atomically approves a PENDING payment request and grants credits.
        Returns: (success: bool, message: str, payment_data: Optional[dict], new_balance: int)
        """
        with db_transaction() as conn:
            cursor = conn.cursor()

            # 1. Lock and check payment record
            cursor.execute(
                "SELECT * FROM payment_receipts WHERE id = ?",
                (payment_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False, "Payment request not found", None, 0

            payment = dict(row)
            user_id = payment.get("user_id") or _resolve_user_id(cursor, payment.get("telegram_user_id"))
            if not user_id:
                return False, "Target user not found", None, 0

            if payment["status"] != "PENDING":
                cursor.execute(
                    "SELECT balance_after FROM credit_transactions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                    (user_id,)
                )
                bal_row = cursor.fetchone()
                current_bal = bal_row["balance_after"] if bal_row else 0
                return False, f"Payment already {payment['status']}", payment, current_bal

            reviewed_by_fk = _resolve_admin_id(cursor, admin_id)

            # 2. Update status to APPROVED
            cursor.execute(
                """
                UPDATE payment_receipts
                SET status = 'APPROVED',
                    reviewed_by = ?,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'PENDING'
                """,
                (reviewed_by_fk, payment_id)
            )

            # 3. Grant credits atomically to the user's ledger in this same transaction
            credits_to_add = payment["credits_requested"]
            package_id = payment.get("package_id", "topup")

            cursor.execute(
                "SELECT balance_after FROM credit_transactions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,)
            )
            last_tx = cursor.fetchone()
            current_balance = last_tx["balance_after"] if last_tx else 0
            new_balance = current_balance + credits_to_add

            cursor.execute(
                """
                INSERT INTO credit_transactions (
                    user_id, amount, transaction_type, reason, balance_after, payment_id
                ) VALUES (?, ?, 'TOPUP_APPROVAL', ?, ?, ?)
                """,
                (
                    user_id,
                    credits_to_add,
                    f"Top-up approval: {credits_to_add} credits ({package_id}) [Ref: {payment_id}]",
                    new_balance,
                    payment_id
                )
            )

            payment["status"] = "APPROVED"
            payment["reviewed_by"] = admin_id

            logger.info(
                "Admin %s APPROVED payment %s: granted %d credits to user_id %s (New balance: %d)",
                admin_id, payment_id, credits_to_add, user_id, new_balance
            )
            return True, "Payment approved successfully", payment, new_balance

    @staticmethod
    def reject_payment(
        payment_id: str,
        admin_id: int,
        reason: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Atomically marks a PENDING payment request as REJECTED.
        Returns: (success: bool, message: str, payment_data: Optional[dict])
        """
        with db_transaction() as conn:
            cursor = conn.cursor()

            # 1. Lock and check payment record
            cursor.execute(
                "SELECT * FROM payment_receipts WHERE id = ?",
                (payment_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False, "Payment request not found", None

            payment = dict(row)
            if payment["status"] != "PENDING":
                return False, f"Payment already {payment['status']}", payment

            reviewed_by_fk = _resolve_admin_id(cursor, admin_id)

            # 2. Update status to REJECTED
            cursor.execute(
                """
                UPDATE payment_receipts
                SET status = 'REJECTED',
                    reviewed_by = ?,
                    rejection_reason = ?,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'PENDING'
                """,
                (reviewed_by_fk, reason, payment_id)
            )

            payment["status"] = "REJECTED"
            payment["reviewed_by"] = admin_id
            payment["rejection_reason"] = reason

            logger.info("Admin %s REJECTED payment %s for user %s", admin_id, payment_id, payment.get("telegram_user_id"))
            return True, "Payment rejected", payment
