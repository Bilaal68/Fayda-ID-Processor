"""
Job Repository

Data access layer for document processing jobs created by Telegram users,
storing and tracking job lifecycles in the central processing_records table.
"""

from typing import Any, Dict, List, Optional
from database.database import db_session
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


class JobRepository:
    """Repository handling job status persistence in the unified processing_records table."""

    @staticmethod
    def create_job(
        job_id: str,
        telegram_user_id: int,
        credit_cost: int = 1,
        input_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        with db_session() as conn:
            cursor = conn.cursor()
            user_id = _resolve_user_id(cursor, telegram_user_id)
            if not user_id:
                from database.repositories.user_repository import UserRepository
                user = UserRepository.get_or_create_user(telegram_user_id=telegram_user_id)
                user_id = user["id"]

            cursor.execute(
                """
                INSERT INTO processing_records (
                    user_id, processing_type, document_count, credit_cost, status, request_id
                ) VALUES (?, 'Fayda PDF', 1, ?, 'PENDING', ?)
                """,
                (user_id, credit_cost, job_id)
            )
        logger.info("Created processing record %s for user %s [cost: %d]", job_id, telegram_user_id, credit_cost)
        return JobRepository.get_job(job_id) or {
            "id": job_id,
            "telegram_user_id": telegram_user_id,
            "status": "PENDING",
            "credit_cost": credit_cost,
            "input_filename": input_filename
        }

    @staticmethod
    def update_status(
        job_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        with db_session() as conn:
            cursor = conn.cursor()
            completed_clause = ", completed_at = CURRENT_TIMESTAMP" if status in ("COMPLETED", "FAILED") else ""
            cursor.execute(
                f"""
                UPDATE processing_records
                SET status = ?, failure_reason = ? {completed_clause}
                WHERE request_id = ?
                """,
                (status, error_message, job_id)
            )
            logger.info("Updated job %s status -> %s (error: %s)", job_id, status, error_message)
            return cursor.rowcount > 0

    @staticmethod
    def get_job(job_id: str) -> Optional[Dict[str, Any]]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM processing_records WHERE request_id = ?", (job_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_user_jobs(
        telegram_user_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        with db_session() as conn:
            cursor = conn.cursor()
            user_id = _resolve_user_id(cursor, telegram_user_id)
            if not user_id:
                return []
            cursor.execute(
                """
                SELECT * FROM processing_records
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit)
            )
            return [dict(r) for r in cursor.fetchall()]
