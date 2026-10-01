from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import sqlite3
from database import db_session, db_transaction

class UserModel:
    @staticmethod
    def create(
        email: str,
        password_hash: str,
        full_name: str,
        role: str = "user",
        is_verified: bool = False
    ) -> Optional[Dict[str, Any]]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (email, password_hash, full_name, role, is_verified, status)
                VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (email.strip().lower(), password_hash, full_name.strip(), role, 1 if is_verified else 0)
            )
            user_id = cursor.lastrowid
        return UserModel.get_by_id(user_id)


    @staticmethod
    def get_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            return UserModel.to_dict(row) if row else None

    @staticmethod
    def get_by_email(email: str) -> Optional[Dict[str, Any]]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email.strip().lower(),))
            row = cursor.fetchone()
            return UserModel.to_dict(row) if row else None

    @staticmethod
    def update_status(user_id: int, status: str) -> bool:
        if status not in ("active", "suspended"):
            return False
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, user_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def update_verification(user_id: int, is_verified: bool = True) -> bool:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_verified = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (1 if is_verified else 0, user_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def update_password(user_id: int, new_password_hash: str) -> bool:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_password_hash, user_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def update_last_activity(user_id: int):
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE id = ?",
                (user_id,)
            )

    @staticmethod
    def list_users(search: Optional[str] = None, limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        with db_session() as conn:
            cursor = conn.cursor()
            base_query = "FROM users"
            params: List[Any] = []

            if search:
                base_query += " WHERE email LIKE ? OR full_name LIKE ?"
                like_term = f"%{search.strip()}%"
                params.extend([like_term, like_term])

            cursor.execute(f"SELECT COUNT(*) {base_query}", tuple(params))
            total_count = cursor.fetchone()[0]

            cursor.execute(
                f"SELECT * {base_query} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params + [limit, offset])
            )
            rows = cursor.fetchall()
            return [UserModel.to_dict(r, include_sensitive=False) for r in rows], total_count

    @staticmethod
    def to_dict(row: sqlite3.Row, include_sensitive: bool = False) -> Dict[str, Any]:
        data = {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"],
            "role": row["role"],
            "status": row["status"],
            "is_verified": bool(row["is_verified"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "last_activity": str(row["last_activity"]) if row["last_activity"] else None,
        }
        if include_sensitive:
            data["password_hash"] = row["password_hash"]
        return data


class CreditLedgerModel:
    @staticmethod
    def get_balance(user_id: int) -> int:
        """Returns the current credit balance from the latest transaction or 0."""
        with db_session() as conn:
            cursor = conn.cursor()
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
    def get_user_stats(user_id: int) -> Dict[str, int]:
        """Calculates total credits granted, used, and current balance."""
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS total_received,
                    COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) AS total_used
                FROM credit_transactions
                WHERE user_id = ?
                """,
                (user_id,)
            )
            row = cursor.fetchone()
            total_received = row["total_received"]
            total_used = row["total_used"]
            current_balance = total_received - total_used
            return {
                "current_credits": max(0, current_balance),
                "total_credits_received": total_received,
                "total_credits_used": total_used,
            }

    @staticmethod
    def record_transaction(
        user_id: int,
        amount: int,
        transaction_type: str,
        reason: str,
        admin_id: Optional[int] = None,
        processing_id: Optional[int] = None
    ) -> Tuple[bool, str, int]:
        """
        Atomically records a credit transaction with immediate row locking.
        Returns: (success: bool, message: str, new_balance: int)
        """
        with db_transaction() as conn:
            cursor = conn.cursor()

            # 1. Fetch current balance with row locking
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

            # Prevent negative balances
            if new_balance < 0:
                return False, f"Insufficient credits. Balance is {current_balance}, requested deduction is {abs(amount)}", current_balance

            # 2. Insert ledger record
            cursor.execute(
                """
                INSERT INTO credit_transactions (
                    user_id, amount, transaction_type, reason,
                    balance_after, admin_id, processing_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, amount, transaction_type, reason, new_balance, admin_id, processing_id)
            )

            return True, "Success", new_balance

    @staticmethod
    def get_history(user_id: Optional[int] = None, limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        with db_session() as conn:
            cursor = conn.cursor()
            base_query = """
                FROM credit_transactions ct
                LEFT JOIN users u ON ct.user_id = u.id
                LEFT JOIN users a ON ct.admin_id = a.id
            """
            params: List[Any] = []

            if user_id is not None:
                base_query += " WHERE ct.user_id = ?"
                params.append(user_id)

            cursor.execute(f"SELECT COUNT(*) {base_query}", tuple(params))
            total_count = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT
                    ct.*,
                    u.email AS user_email,
                    u.full_name AS user_name,
                    a.email AS admin_email,
                    a.full_name AS admin_name
                {base_query}
                ORDER BY ct.id DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [limit, offset])
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                results.append({
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "user_email": r["user_email"],
                    "user_name": r["user_name"],
                    "amount": r["amount"],
                    "transaction_type": r["transaction_type"],
                    "reason": r["reason"],
                    "balance_after": r["balance_after"],
                    "admin_id": r["admin_id"],
                    "admin_email": r["admin_email"],
                    "admin_name": r["admin_name"],
                    "processing_id": r["processing_id"],
                    "created_at": str(r["created_at"]),
                })
            return results, total_count


class ProcessingRecordModel:
    @staticmethod
    def create(
        user_id: int,
        processing_type: str,
        document_count: int,
        credit_cost: int,
        request_id: str
    ) -> int:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO processing_records (
                    user_id, processing_type, document_count,
                    credit_cost, status, request_id
                ) VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (user_id, processing_type, document_count, credit_cost, request_id)
            )
            return cursor.lastrowid

    @staticmethod
    def mark_completed(record_id: int):
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE processing_records
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (record_id,)
            )

    @staticmethod
    def mark_failed(record_id: int, failure_reason: str):
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE processing_records
                SET status = 'failed', failure_reason = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (failure_reason[:500], record_id)
            )

    @staticmethod
    def get_stats(user_id: Optional[int] = None) -> Dict[str, int]:
        with db_session() as conn:
            cursor = conn.cursor()
            where = "WHERE user_id = ?" if user_id is not None else ""
            params = (user_id,) if user_id is not None else ()

            cursor.execute(
                f"""
                SELECT
                    COALESCE(SUM(document_count), 0) AS total_documents,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN document_count ELSE 0 END), 0) AS successful,
                    COALESCE(SUM(CASE WHEN status = 'failed' THEN document_count ELSE 0 END), 0) AS failed
                FROM processing_records
                {where}
                """,
                params
            )
            row = cursor.fetchone()
            return {
                "total_documents": row["total_documents"],
                "successful_documents": row["successful"],
                "failed_documents": row["failed"],
            }

    @staticmethod
    def get_history(user_id: Optional[int] = None, limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        with db_session() as conn:
            cursor = conn.cursor()
            base_query = """
                FROM processing_records pr
                LEFT JOIN users u ON pr.user_id = u.id
            """
            params: List[Any] = []

            if user_id is not None:
                base_query += " WHERE pr.user_id = ?"
                params.append(user_id)

            cursor.execute(f"SELECT COUNT(*) {base_query}", tuple(params))
            total_count = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT
                    pr.*,
                    u.email AS user_email,
                    u.full_name AS user_name
                {base_query}
                ORDER BY pr.id DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [limit, offset])
            )
            rows = cursor.fetchall()
            results = []
            for r in rows:
                results.append({
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "user_email": r["user_email"],
                    "user_name": r["user_name"],
                    "processing_type": r["processing_type"],
                    "document_count": r["document_count"],
                    "credit_cost": r["credit_cost"],
                    "status": r["status"],
                    "failure_reason": r["failure_reason"],
                    "request_id": r["request_id"],
                    "created_at": str(r["created_at"]),
                    "completed_at": str(r["completed_at"]) if r["completed_at"] else None,
                })
            return results, total_count


class AdminStatsModel:
    @staticmethod
    def get_overview_stats() -> Dict[str, Any]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total_users,
                    COALESCE(SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), 0) as active_users,
                    COALESCE(SUM(CASE WHEN status = 'suspended' THEN 1 ELSE 0 END), 0) as suspended_users
                FROM users
            """)
            u_row = cursor.fetchone()

            cursor.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total_credits_issued,
                    COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as total_credits_used
                FROM credit_transactions
            """)
            c_row = cursor.fetchone()

            p_stats = ProcessingRecordModel.get_stats(None)

            return {
                "total_users": u_row["total_users"],
                "active_users": u_row["active_users"],
                "suspended_users": u_row["suspended_users"],
                "total_credits_issued": c_row["total_credits_issued"],
                "total_credits_used": c_row["total_credits_used"],
                "total_documents": p_stats["total_documents"],
                "successful_documents": p_stats["successful_documents"],
                "failed_documents": p_stats["failed_documents"]
            }

