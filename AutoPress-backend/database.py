import sqlite3
import os
import threading
from contextlib import contextmanager
from typing import Generator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("AUTOPRESS_DB_PATH", os.path.join(BASE_DIR, "autopress.db"))

_lock = threading.RLock()

def get_db_connection() -> sqlite3.Connection:
    """Create a SQLite connection configured for high concurrency and safety."""
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30.0,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    conn.row_factory = sqlite3.Row
    # Enable Write-Ahead Logging for high concurrency read/writes
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn

@contextmanager
def db_session() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for regular read/write operations with auto-commit/rollback."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@contextmanager
def db_transaction() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for immediate exclusive transactions (e.g. credit deductions)."""
    with _lock:
        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

def init_db():
    """Initializes tables and indexes if they do not exist."""
    with db_session() as conn:
        cursor = conn.cursor()

        # 1. Users Table
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
                source TEXT NOT NULL DEFAULT 'website',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Migrations: ensure columns exist on existing users table
        cursor.execute("PRAGMA table_info(users);")
        columns = [row[1] for row in cursor.fetchall()]
        if "firebase_uid" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN firebase_uid TEXT;")
        if "telegram_user_id" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN telegram_user_id INTEGER;")
        if "telegram_username" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN telegram_username TEXT;")
        if "first_name" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT;")
        if "last_name" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN last_name TEXT;")
        if "language" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN language TEXT NOT NULL DEFAULT 'am';")
        if "source" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN source TEXT NOT NULL DEFAULT 'website';")

        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid);")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_user_id ON users(telegram_user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_source ON users(source);")

        # 2. Processing Records Table
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

        # 3. Credit Transactions Ledger Table
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 4. Payment Receipts Table
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

        # Migrations: ensure columns exist in payment_receipts
        cursor.execute("PRAGMA table_info(payment_receipts);")
        p_cols = [row[1] for row in cursor.fetchall()]
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

        # Migrations: ensure payment_id and job_id exist on credit_transactions
        cursor.execute("PRAGMA table_info(credit_transactions);")
        ct_cols = [row[1] for row in cursor.fetchall()]
        if "payment_id" not in ct_cols:
            cursor.execute("ALTER TABLE credit_transactions ADD COLUMN payment_id TEXT;")
        if "job_id" not in ct_cols:
            cursor.execute("ALTER TABLE credit_transactions ADD COLUMN job_id TEXT;")

        # 5. Indexes for optimal query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_credits_user ON credit_transactions(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_credits_date ON credit_transactions(created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_credits_payment ON credit_transactions(payment_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_user ON processing_records(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_date ON processing_records(created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_request_id ON processing_records(request_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payment_receipts(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_user ON payment_receipts(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_tg ON payment_receipts(telegram_user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_created ON payment_receipts(created_at);")

        print("✅ SQLite database initialized at:", DB_PATH)
