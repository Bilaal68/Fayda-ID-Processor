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
        normalized_email = email.strip().lower()
        try:
            with db_session() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (email, password_hash, full_name, role, is_verified, status)
                    VALUES (?, ?, ?, ?, ?, 'active')
                    """,
                    (normalized_email, password_hash, full_name.strip(), role, 1 if is_verified else 0)
                )
                user_id = cursor.lastrowid

            if user_id and role != "admin":
                import os
                default_credits = int(os.environ.get("DEFAULT_SIGNUP_CREDITS", 2))
                if default_credits > 0:
                    CreditLedgerModel.record_transaction(
                        user_id=user_id,
                        amount=default_credits,
                        transaction_type="ADMIN_GRANT",
                        reason=f"Welcome bonus ({default_credits} credits on registration)"
                    )

            return UserModel.get_by_id(user_id)
        except sqlite3.IntegrityError:
            return None



    @staticmethod
    def get_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            return UserModel.to_dict(row) if row else None

    @staticmethod
    def get_by_firebase_uid(firebase_uid: str) -> Optional[Dict[str, Any]]:
        if not firebase_uid:
            return None
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE firebase_uid = ?", (firebase_uid.strip(),))
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
    def link_firebase_uid(user_id: int, firebase_uid: str) -> bool:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET firebase_uid = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (firebase_uid.strip(), user_id)
            )
            return cursor.rowcount > 0

    @staticmethod
    def create_or_sync_firebase_user(
        firebase_uid: str,
        email: str,
        full_name: str = "",
        is_verified: bool = False,
        role: str = "user"
    ) -> Optional[Dict[str, Any]]:
        """
        Idempotently resolves or provisions an AutoPress user for a Firebase UID:
        1. Checks if user already exists by firebase_uid.
        2. If not, checks if an existing user matches by email -> links firebase_uid.
        3. If no existing user, creates a new user record.
        """
        normalized_email = email.strip().lower()
        clean_uid = firebase_uid.strip()
        display_name = full_name.strip() or normalized_email.split("@")[0]

        # 1. Existing by firebase_uid
        user = UserModel.get_by_firebase_uid(clean_uid)
        if user:
            needs_update = False
            updates = {}
            # Always sync role upward (user→admin), never demote
            if role == "admin" and user.get("role") != "admin":
                updates["role"] = "admin"
                needs_update = True
            # Sync verification status if changed
            if is_verified and not user.get("is_verified"):
                updates["is_verified"] = 1
                needs_update = True
            if needs_update:
                with db_session() as conn:
                    for col, val in updates.items():
                        conn.execute(
                            f"UPDATE users SET {col} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (val, user["id"])
                        )
            return UserModel.get_by_id(user["id"])

        # 2. Existing by email (linking legacy accounts)
        user = UserModel.get_by_email(normalized_email)
        if user:
            UserModel.link_firebase_uid(user["id"], clean_uid)
            # Sync role upward
            if role == "admin" and user.get("role") != "admin":
                with db_session() as conn:
                    conn.execute(
                        "UPDATE users SET role = 'admin', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (user["id"],)
                    )
            if is_verified and not user.get("is_verified"):
                UserModel.update_verification(user["id"], True)
            return UserModel.get_by_id(user["id"])

        # 3. Create fresh user
        try:
            with db_session() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (email, password_hash, full_name, role, is_verified, status, firebase_uid)
                    VALUES (?, '', ?, ?, ?, 'active', ?)
                    """,
                    (normalized_email, display_name, role, 1 if is_verified else 0, clean_uid)
                )
                user_id = cursor.lastrowid

            if user_id and role != "admin":
                import os
                default_credits = int(os.environ.get("DEFAULT_SIGNUP_CREDITS", 2))
                if default_credits > 0:
                    CreditLedgerModel.record_transaction(
                        user_id=user_id,
                        amount=default_credits,
                        transaction_type="ADMIN_GRANT",
                        reason=f"Welcome bonus ({default_credits} credits on registration)"
                    )

            return UserModel.get_by_id(user_id)
        except sqlite3.IntegrityError:
            # Handle potential concurrent insert
            return UserModel.get_by_firebase_uid(clean_uid) or UserModel.get_by_email(normalized_email)

    @staticmethod
    def get_by_telegram_id(telegram_user_id: int) -> Optional[Dict[str, Any]]:
        if not telegram_user_id:
            return None
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE telegram_user_id = ?", (telegram_user_id,))
            row = cursor.fetchone()
            if row:
                return UserModel.to_dict(row)
            # Fallback to synthetic email pattern
            cursor.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (f"telegram_{telegram_user_id}@autopress.bot",))
            row = cursor.fetchone()
            return UserModel.to_dict(row) if row else None

    @staticmethod
    def get_or_create_telegram_user(
        telegram_user_id: int,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
        full_name: str = ""
    ) -> Dict[str, Any]:
        """
        Idempotently resolves or provisions a unified AutoPress user for a Telegram user ID.
        Stores telegram_user_id, telegram_username, first_name, last_name, source='telegram'.
        """
        user = UserModel.get_by_telegram_id(telegram_user_id)
        clean_username = username.strip().lstrip("@") if username else ""
        clean_fn = first_name.strip() if first_name else ""
        clean_ln = last_name.strip() if last_name else ""
        name_candidate = full_name.strip() or f"{clean_fn} {clean_ln}".strip() or (f"@{clean_username}" if clean_username else f"Telegram User {telegram_user_id}")

        if user:
            # Update latest username, names, and last activity
            with db_session() as conn:
                conn.execute(
                    """
                    UPDATE users
                    SET telegram_user_id = ?,
                        telegram_username = COALESCE(NULLIF(?, ''), telegram_username),
                        first_name = COALESCE(NULLIF(?, ''), first_name),
                        last_name = COALESCE(NULLIF(?, ''), last_name),
                        full_name = CASE WHEN full_name LIKE 'Telegram User %' OR full_name LIKE '@%' THEN ? ELSE full_name END,
                        last_activity = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (telegram_user_id, clean_username, clean_fn, clean_ln, name_candidate, user["id"])
                )
            return UserModel.get_by_id(user["id"])

        tg_email = f"telegram_{telegram_user_id}@autopress.bot"
        try:
            with db_session() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (
                        email, password_hash, full_name, role, is_verified, status,
                        telegram_user_id, telegram_username, first_name, last_name, source
                    )
                    VALUES (?, '', ?, 'user', 1, 'active', ?, ?, ?, ?, 'telegram')
                    """,
                    (tg_email, name_candidate, telegram_user_id, clean_username, clean_fn, clean_ln)
                )
                user_id = cursor.lastrowid

            import os
            default_credits = int(os.environ.get("DEFAULT_SIGNUP_CREDITS", 2))
            if default_credits > 0 and user_id:
                CreditLedgerModel.record_transaction(
                    user_id=user_id,
                    amount=default_credits,
                    transaction_type="ADMIN_GRANT",
                    reason=f"Welcome bonus ({default_credits} credits on registration)"
                )
            return UserModel.get_by_id(user_id)
        except sqlite3.IntegrityError:
            return UserModel.get_by_telegram_id(telegram_user_id) or UserModel.get_by_email(tg_email)

    @staticmethod
    def update_role(user_id: int, role: str) -> bool:
        if role not in ("user", "admin"):
            return False
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET role = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (role, user_id)
            )
            return cursor.rowcount > 0

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
    def list_users(
        search: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int, Dict[str, int]]:
        with db_session() as conn:
            cursor = conn.cursor()

            # Breakdown counts
            cursor.execute("""
                SELECT
                    COUNT(*) as total_all,
                    COALESCE(SUM(CASE WHEN source = 'website' THEN 1 ELSE 0 END), 0) as total_website,
                    COALESCE(SUM(CASE WHEN source = 'telegram' THEN 1 ELSE 0 END), 0) as total_telegram,
                    COALESCE(SUM(CASE WHEN source = 'both' THEN 1 ELSE 0 END), 0) as total_both,
                    COALESCE(SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), 0) as total_active,
                    COALESCE(SUM(CASE WHEN status = 'suspended' THEN 1 ELSE 0 END), 0) as total_suspended
                FROM users
            """)
            c_row = cursor.fetchone()
            counts = {
                "all": c_row["total_all"] if c_row else 0,
                "website": c_row["total_website"] if c_row else 0,
                "telegram": c_row["total_telegram"] if c_row else 0,
                "both": c_row["total_both"] if c_row else 0,
                "active": c_row["total_active"] if c_row else 0,
                "suspended": c_row["total_suspended"] if c_row else 0
            }

            base_query = "FROM users WHERE 1=1"
            params: List[Any] = []

            if source and source.lower() in ('website', 'telegram', 'both'):
                base_query += " AND source = ?"
                params.append(source.lower())

            if status and status.lower() in ('active', 'suspended'):
                base_query += " AND status = ?"
                params.append(status.lower())

            if search:
                like_term = f"%{search.strip()}%"
                base_query += " AND (email LIKE ? OR full_name LIKE ? OR telegram_username LIKE ? OR first_name LIKE ? OR last_name LIKE ? OR CAST(telegram_user_id AS TEXT) LIKE ?)"
                params.extend([like_term, like_term, like_term, like_term, like_term, like_term])

            cursor.execute(f"SELECT COUNT(*) {base_query}", tuple(params))
            total_count = cursor.fetchone()[0]

            cursor.execute(
                f"SELECT * {base_query} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params + [limit, offset])
            )
            rows = cursor.fetchall()
            return [UserModel.to_dict(r, include_sensitive=False) for r in rows], total_count, counts

    @staticmethod
    def to_dict(row: sqlite3.Row, include_sensitive: bool = False) -> Dict[str, Any]:
        row_keys = row.keys()
        raw_email = row["email"] if "email" in row_keys else ""
        is_synthetic = bool(raw_email and raw_email.startswith("telegram_") and raw_email.endswith("@autopress.bot"))
        display_email = "" if is_synthetic else raw_email

        data = {
            "id": row["id"],
            "email": display_email,
            "raw_email": raw_email,
            "full_name": row["full_name"],
            "first_name": row["first_name"] if "first_name" in row_keys and row["first_name"] else "",
            "last_name": row["last_name"] if "last_name" in row_keys and row["last_name"] else "",
            "role": row["role"],
            "status": row["status"],
            "is_verified": bool(row["is_verified"]),
            "firebase_uid": row["firebase_uid"] if "firebase_uid" in row_keys else None,
            "telegram_user_id": row["telegram_user_id"] if "telegram_user_id" in row_keys else None,
            "telegram_username": row["telegram_username"] if "telegram_username" in row_keys else None,
            "source": row["source"] if "source" in row_keys and row["source"] else ("telegram" if is_synthetic else "website"),
            "current_credits": row["current_credits"] if "current_credits" in row_keys else CreditLedgerModel.get_balance(row["id"]),
            "total_documents": row["total_documents"] if "total_documents" in row_keys else 0,
            "successful_documents": row["successful_documents"] if "successful_documents" in row_keys else 0,
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
        processing_id: Optional[int] = None,
        payment_id: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> Tuple[bool, str, int]:
        """
        Atomically records a credit transaction with immediate row locking.
        Guarantees idempotency when job_id or payment_id is provided.
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

            # Idempotency check for jobs
            if job_id:
                if amount < 0:
                    cursor.execute(
                        """
                        SELECT id FROM credit_transactions
                        WHERE user_id = ? AND job_id = ? AND amount < 0
                        """,
                        (user_id, job_id)
                    )
                    if cursor.fetchone():
                        return True, "Idempotent: deduction already recorded", current_balance
                elif transaction_type == "PROCESSING_REFUND":
                    cursor.execute(
                        """
                        SELECT id FROM credit_transactions
                        WHERE user_id = ? AND job_id = ? AND transaction_type = 'PROCESSING_REFUND'
                        """,
                        (user_id, job_id)
                    )
                    if cursor.fetchone():
                        return True, "Idempotent: refund already recorded", current_balance

            new_balance = current_balance + amount

            # Prevent negative balances
            if new_balance < 0:
                return False, f"Insufficient credits. Balance is {current_balance}, requested deduction is {abs(amount)}", current_balance

            # 2. Insert ledger record
            cursor.execute(
                """
                INSERT INTO credit_transactions (
                    user_id, amount, transaction_type, reason,
                    balance_after, admin_id, processing_id, payment_id, job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, amount, transaction_type, reason, new_balance, admin_id, processing_id, payment_id, job_id)
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
                    "payment_id": r["payment_id"] if "payment_id" in r.keys() else None,
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


class PaymentModel:
    """Authoritative repository for manual top-up payment requests."""

    @staticmethod
    def create(
        payment_id: str,
        user_id: Optional[int] = None,
        telegram_user_id: Optional[int] = None,
        telegram_username: Optional[str] = None,
        package_id: str = "credits_10",
        credits_requested: int = 10,
        amount_etb: float = 100.0,
        payment_method: str = "Bank Account (CBE)",
        screenshot_file_id: Optional[str] = None,
        screenshot_url: Optional[str] = None
    ) -> Dict[str, Any]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM payment_receipts WHERE id = ?", (payment_id,))
            if cursor.fetchone():
                return PaymentModel.get_by_id(payment_id)

            cursor.execute(
                """
                INSERT INTO payment_receipts (
                    id, user_id, telegram_user_id, telegram_username,
                    package_id, credits_requested, amount_etb, payment_method,
                    screenshot_file_id, screenshot_url, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    payment_id,
                    user_id,
                    telegram_user_id,
                    telegram_username,
                    package_id,
                    credits_requested,
                    amount_etb,
                    payment_method,
                    screenshot_file_id,
                    screenshot_url
                )
            )
        return PaymentModel.get_by_id(payment_id)

    @staticmethod
    def get_by_id(payment_id: str) -> Optional[Dict[str, Any]]:
        with db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT p.*, u.email AS user_email, u.full_name AS user_name
                FROM payment_receipts p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.id = ?
                """,
                (payment_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_payments(
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int, Dict[str, int]]:
        with db_session() as conn:
            cursor = conn.cursor()

            # Status counts
            cursor.execute("""
                SELECT
                    COUNT(*) as total_all,
                    COALESCE(SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END), 0) as total_pending,
                    COALESCE(SUM(CASE WHEN status = 'APPROVED' THEN 1 ELSE 0 END), 0) as total_approved,
                    COALESCE(SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END), 0) as total_rejected
                FROM payment_receipts
            """)
            c_row = cursor.fetchone()
            counts = {
                "all": c_row["total_all"] if c_row else 0,
                "pending": c_row["total_pending"] if c_row else 0,
                "approved": c_row["total_approved"] if c_row else 0,
                "rejected": c_row["total_rejected"] if c_row else 0
            }

            base_query = """
                FROM payment_receipts p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE 1=1
            """
            params: List[Any] = []

            if status and status.upper() in ("PENDING", "APPROVED", "REJECTED"):
                base_query += " AND p.status = ?"
                params.append(status.upper())

            if search:
                like_term = f"%{search.strip()}%"
                base_query += " AND (p.id LIKE ? OR p.telegram_username LIKE ? OR CAST(p.telegram_user_id AS TEXT) LIKE ? OR u.email LIKE ? OR p.payment_method LIKE ?)"
                params.extend([like_term, like_term, like_term, like_term, like_term])

            cursor.execute(f"SELECT COUNT(*) {base_query}", tuple(params))
            total_count = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT
                    p.*,
                    u.email AS user_email,
                    u.full_name AS user_name
                {base_query}
                ORDER BY
                    CASE WHEN p.status = 'PENDING' THEN 0 ELSE 1 END ASC,
                    p.created_at DESC,
                    p.rowid DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [limit, offset])
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows], total_count, counts

    @staticmethod
    def approve_payment(
        payment_id: str,
        admin_id: int,
        admin_email: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]], int]:
        """
        Atomically approves a PENDING payment, grants credits, and triggers Telegram notification.
        Guarantees strict idempotency at the database transaction level.
        """
        from services.telegram_service import send_telegram_notification

        # Pre-resolve Telegram user outside transaction to prevent SQLite connection lock contention
        pre_payment = PaymentModel.get_by_id(payment_id)
        if not pre_payment:
            return False, "Payment request not found.", None, 0

        pre_tg_id = pre_payment.get("telegram_user_id")
        if pre_tg_id:
            UserModel.get_or_create_telegram_user(
                telegram_user_id=pre_tg_id,
                username=pre_payment.get("telegram_username") or ""
            )

        with db_transaction() as conn:
            cursor = conn.cursor()

            # 1. Fetch payment with row lock
            cursor.execute("SELECT * FROM payment_receipts WHERE id = ?", (payment_id,))
            row = cursor.fetchone()
            if not row:
                return False, "Payment request not found.", None, 0

            payment = dict(row)

            # 2. Strict Idempotency Check
            if payment["status"] == "APPROVED":
                # Find current balance
                bal = 0
                if payment.get("user_id"):
                    bal = CreditLedgerModel.get_balance(payment["user_id"])
                return False, "Payment has already been APPROVED. No duplicate credits added.", payment, bal

            if payment["status"] == "REJECTED":
                return False, "Payment was already REJECTED. Cannot approve a rejected payment.", payment, 0

            if payment["status"] != "PENDING":
                return False, f"Payment is in '{payment['status']}' state.", payment, 0

            # 3. Resolve target AutoPress user on current connection
            target_user_id = payment.get("user_id")
            tg_id = payment.get("telegram_user_id")
            if tg_id:
                cursor.execute("SELECT id FROM users WHERE telegram_user_id = ?", (tg_id,))
                u_row = cursor.fetchone()
                if u_row:
                    target_user_id = u_row["id"]
                    cursor.execute(
                        "UPDATE payment_receipts SET user_id = ? WHERE id = ?",
                        (target_user_id, payment_id)
                    )

            if not target_user_id:
                target_user_id = admin_id

            # Secondary idempotency check: verify credit was not already granted for this payment
            cursor.execute(
                "SELECT id FROM credit_transactions WHERE payment_id = ? AND transaction_type = 'TOPUP_GRANT'",
                (payment_id,)
            )
            if cursor.fetchone():
                bal = CreditLedgerModel.get_balance(target_user_id)
                return False, "Credits for this payment have already been granted.", payment, bal

            # 4. Mark payment as APPROVED
            cursor.execute(
                """
                UPDATE payment_receipts
                SET status = 'APPROVED',
                    reviewed_by = ?,
                    reviewed_by_email = ?,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (admin_id, admin_email, payment_id)
            )

            # 5. Grant Credits via Authoritative Credit Ledger in this exact atomic transaction
            credits_to_add = int(payment["credits_requested"])
            method = payment.get("payment_method", "Top-Up")
            reason_text = f"Top-Up: {credits_to_add} Credits via {method} (Payment {payment_id})"

            cursor.execute(
                """
                SELECT balance_after FROM credit_transactions
                WHERE user_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (target_user_id,)
            )
            last_bal_row = cursor.fetchone()
            current_bal = last_bal_row["balance_after"] if last_bal_row else 0
            new_balance = current_bal + credits_to_add

            cursor.execute(
                """
                INSERT INTO credit_transactions (
                    user_id, amount, transaction_type, reason,
                    balance_after, admin_id, processing_id, payment_id
                ) VALUES (?, ?, 'TOPUP_GRANT', ?, ?, ?, NULL, ?)
                """,
                (target_user_id, credits_to_add, reason_text, new_balance, admin_id, payment_id)
            )

        # 6. Dispatch Telegram notification (non-blocking / outside tx lock)
        notification_sent = False
        tg_id = payment.get("telegram_user_id")
        if tg_id:
            user_notify_text = (
                "🎉 *Payment Approved!*\n\n"
                f"*{credits_to_add} credits* have been added to your AutoPress account.\n"
                f"💰 *Current Balance:* {new_balance} credits.\n\n"
                "Thank you for using AutoPress! You can now upload and process your Fayda PDFs."
            )
            notification_sent = bool(send_telegram_notification(tg_id, user_notify_text))

        updated = PaymentModel.get_by_id(payment_id)
        if updated:
            updated["notification_sent"] = notification_sent
        return True, f"Payment successfully approved. +{credits_to_add} credits added.", updated, new_balance

    @staticmethod
    def reject_payment(
        payment_id: str,
        admin_id: int,
        admin_email: str,
        reason: str = ""
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Atomically rejects a PENDING payment. Adds 0 credits and triggers Telegram notification.
        """
        from services.telegram_service import send_telegram_notification

        clean_reason = reason.strip() if reason else "Receipt verification failed."

        with db_transaction() as conn:
            cursor = conn.cursor()

            # 1. Fetch payment with row lock
            cursor.execute("SELECT * FROM payment_receipts WHERE id = ?", (payment_id,))
            row = cursor.fetchone()
            if not row:
                return False, "Payment request not found.", None

            payment = dict(row)

            # 2. Idempotency and State Checks
            if payment["status"] == "APPROVED":
                return False, "Cannot reject an already APPROVED payment.", payment

            if payment["status"] == "REJECTED":
                return False, "Payment has already been REJECTED.", payment

            # 3. Mark as REJECTED
            cursor.execute(
                """
                UPDATE payment_receipts
                SET status = 'REJECTED',
                    rejection_reason = ?,
                    reviewed_by = ?,
                    reviewed_by_email = ?,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (clean_reason, admin_id, admin_email, payment_id)
            )

        # 4. Dispatch Telegram notification (outside tx lock)
        notification_sent = False
        tg_id = payment.get("telegram_user_id")
        if tg_id:
            user_notify_text = (
                "❌ *Payment Verification Notice*\n\n"
                f"Your payment request (`{payment_id}`) could not be verified.\n\n"
                f"Reason: {clean_reason}\n\n"
                "No credits were added. If you have questions, please contact support."
            )
            notification_sent = bool(send_telegram_notification(tg_id, user_notify_text))

        updated = PaymentModel.get_by_id(payment_id)
        if updated:
            updated["notification_sent"] = notification_sent
        return True, "Payment request successfully rejected.", updated


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

            cursor.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END), 0) as pending_payments,
                    COALESCE(SUM(CASE WHEN status = 'APPROVED' THEN amount_etb ELSE 0 END), 0) as total_revenue_etb
                FROM payment_receipts
            """)
            pay_row = cursor.fetchone()

            p_stats = ProcessingRecordModel.get_stats(None)

            return {
                "total_users": u_row["total_users"],
                "active_users": u_row["active_users"],
                "suspended_users": u_row["suspended_users"],
                "total_credits_issued": c_row["total_credits_issued"],
                "total_credits_used": c_row["total_credits_used"],
                "total_documents": p_stats["total_documents"],
                "successful_documents": p_stats["successful_documents"],
                "failed_documents": p_stats["failed_documents"],
                "pending_payments": pay_row["pending_payments"] if pay_row else 0,
                "total_revenue_etb": pay_row["total_revenue_etb"] if pay_row else 0
            }

