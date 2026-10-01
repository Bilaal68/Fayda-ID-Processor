import sqlite3
import os
import threading
from contextlib import contextmanager
from typing import Generator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("AUTOPRESS_DB_PATH", os.path.join(BASE_DIR, "autopress.db"))

_lock = threading.Lock()

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
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                is_verified INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

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

        # 4. Indexes for optimal query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_credits_user ON credit_transactions(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_credits_date ON credit_transactions(created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_user ON processing_records(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_date ON processing_records(created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_request_id ON processing_records(request_id);")

        print("✅ SQLite database initialized at:", DB_PATH)
