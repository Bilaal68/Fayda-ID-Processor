"""
AutoPress Telegram Bot - Database Engine and Session Management

Provides SQLite WAL connection, thread-safe transaction locks,
and unified table management for AutoPress users, credit ledger, jobs, and payments.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Generator
from config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)

_tx_lock = threading.RLock()


def get_db_connection() -> sqlite3.Connection:
    """Create a SQLite connection configured for WAL mode and busy timeout."""
    conn = sqlite3.connect(
        settings.DATABASE_PATH,
        timeout=30.0,
        isolation_level=None,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn


@contextmanager
def db_session() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for standard read/write operations with auto-commit/rollback."""
    with _tx_lock:
        conn = get_db_connection()
        try:
            yield conn
        finally:
            conn.close()


# Alias for backward compatibility
get_connection = db_session


@contextmanager
def db_transaction() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for exclusive atomic transactions (e.g. credit ledger changes)."""
    with _tx_lock:
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        finally:
            conn.close()


def init_db() -> None:
    """Initialize unified database schemas and indexes on central database."""
    with db_session() as conn:
        cursor = conn.cursor()

        # 1. Unified Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT DEFAULT '',
                full_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                is_verified INTEGER NOT NULL DEFAULT 0,
                firebase_uid TEXT UNIQUE,
                telegram_user_id INTEGER UNIQUE,
                telegram_username TEXT,
                first_name TEXT,
                last_name TEXT,
                language TEXT NOT NULL DEFAULT 'am',
                source TEXT NOT NULL DEFAULT 'website',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Migrations: ensure columns exist on users
        cursor.execute("PRAGMA table_info(users);")
        u_cols = {row["name"] for row in cursor.fetchall()}
        if "firebase_uid" not in u_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN firebase_uid TEXT;")
        if "telegram_user_id" not in u_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN telegram_user_id INTEGER;")
        if "telegram_username" not in u_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN telegram_username TEXT;")
        if "first_name" not in u_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT;")
        if "last_name" not in u_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN last_name TEXT;")
        if "language" not in u_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN language TEXT NOT NULL DEFAULT 'am';")
        if "source" not in u_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN source TEXT NOT NULL DEFAULT 'website';")

        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid);")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_user_id ON users(telegram_user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_source ON users(source);")

        # 2. Unified Processing Records Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                processing_type TEXT NOT NULL,
                document_count INTEGER NOT NULL DEFAULT 1,
                credit_cost INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'pending',
                failure_reason TEXT,
                request_id TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
        """)

        # 3. Unified Credit Transactions Ledger Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credit_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                amount INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                reason TEXT,
                balance_after INTEGER NOT NULL,
                admin_id INTEGER REFERENCES users(id),
                processing_id INTEGER REFERENCES processing_records(id),
                payment_id TEXT,
                job_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Migrations: ensure columns exist on credit_transactions
        cursor.execute("PRAGMA table_info(credit_transactions);")
        ct_cols = {row["name"] for row in cursor.fetchall()}
        if "payment_id" not in ct_cols:
            cursor.execute("ALTER TABLE credit_transactions ADD COLUMN payment_id TEXT;")
        if "job_id" not in ct_cols:
            cursor.execute("ALTER TABLE credit_transactions ADD COLUMN job_id TEXT;")

        # 4. Unified Payment Receipts Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_receipts (
                id TEXT PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                telegram_user_id INTEGER,
                telegram_username TEXT,
                package_id TEXT NOT NULL DEFAULT 'credits_10',
                credits_requested INTEGER NOT NULL DEFAULT 10,
                amount_etb REAL NOT NULL DEFAULT 100.0,
                payment_method TEXT NOT NULL DEFAULT 'Bank Account (CBE)',
                screenshot_file_id TEXT,
                screenshot_url TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                rejection_reason TEXT,
                reviewed_by INTEGER REFERENCES users(id),
                reviewed_by_email TEXT,
                reviewed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Migrations: ensure columns exist on payment_receipts
        cursor.execute("PRAGMA table_info(payment_receipts);")
        p_cols = {row["name"] for row in cursor.fetchall()}
        if "telegram_user_id" not in p_cols:
            cursor.execute("ALTER TABLE payment_receipts ADD COLUMN telegram_user_id INTEGER;")
        if "telegram_username" not in p_cols:
            cursor.execute("ALTER TABLE payment_receipts ADD COLUMN telegram_username TEXT;")
        if "screenshot_file_id" not in p_cols:
            cursor.execute("ALTER TABLE payment_receipts ADD COLUMN screenshot_file_id TEXT;")
        if "screenshot_url" not in p_cols:
            cursor.execute("ALTER TABLE payment_receipts ADD COLUMN screenshot_url TEXT;")
        if "rejection_reason" not in p_cols:
            cursor.execute("ALTER TABLE payment_receipts ADD COLUMN rejection_reason TEXT;")
        if "reviewed_by_email" not in p_cols:
            cursor.execute("ALTER TABLE payment_receipts ADD COLUMN reviewed_by_email TEXT;")

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_credits_user ON credit_transactions(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_credits_date ON credit_transactions(created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_user ON processing_records(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_request_id ON processing_records(request_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payment_receipts(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_user ON payment_receipts(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_tg ON payment_receipts(telegram_user_id);")

    logger.info("Unified AutoPress database initialized successfully at: %s", settings.DATABASE_PATH)
