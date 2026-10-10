#!/usr/bin/env python3
"""
AutoPress Balance Reconciliation Script (Read-Only)

Safely connects to both AutoPress backend database and Telegram bot database
using read-only SQLite URIs ('?mode=ro') to identify any balance discrepancies
across Telegram users without modifying either database.
"""

import sys
import os
import argparse
import sqlite3
from typing import Dict, Any, Optional, Tuple


def get_backend_balances(db_path: str) -> Dict[int, Dict[str, Any]]:
    """
    Extracts latest credit balance and transaction count per Telegram user from backend DB.
    Uses SQLite read-only URI mode.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Backend database not found at {db_path}")

    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    users_data: Dict[int, Dict[str, Any]] = {}
    try:
        # Fetch all Telegram users
        cursor.execute("""
            SELECT id, telegram_user_id, email, full_name, created_at
            FROM users
            WHERE telegram_user_id IS NOT NULL
        """)
        users = cursor.fetchall()

        for u in users:
            tg_id = int(u["telegram_user_id"])
            u_id = u["id"]

            # Latest balance
            cursor.execute("""
                SELECT balance_after, created_at
                FROM credit_transactions
                WHERE user_id = ?
                ORDER BY id DESC LIMIT 1
            """, (u_id,))
            last_tx = cursor.fetchone()
            balance = last_tx["balance_after"] if last_tx else 0

            # Count of transactions
            cursor.execute("""
                SELECT COUNT(*) as tx_count
                FROM credit_transactions
                WHERE user_id = ?
            """, (u_id,))
            count_row = cursor.fetchone()
            tx_count = count_row["tx_count"] if count_row else 0

            users_data[tg_id] = {
                "user_id": u_id,
                "telegram_user_id": tg_id,
                "email": u["email"],
                "full_name": u["full_name"],
                "balance": balance,
                "tx_count": tx_count,
            }
    finally:
        conn.close()

    return users_data


def get_bot_balances(db_path: str) -> Dict[int, Dict[str, Any]]:
    """
    Extracts credit balance snapshot and transactions per Telegram user from Bot DB.
    Uses SQLite read-only URI mode.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Bot database not found at {db_path}")

    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    users_data: Dict[int, Dict[str, Any]] = {}
    try:
        # Check if users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            return users_data

        cursor.execute("SELECT id, telegram_user_id, username, full_name FROM users WHERE telegram_user_id IS NOT NULL")
        users = cursor.fetchall()

        for u in users:
            tg_id = int(u["telegram_user_id"])
            u_id = u["id"]

            # Balance from transactions or snapshot
            cursor.execute("""
                SELECT balance_after
                FROM credit_transactions
                WHERE user_id = ?
                ORDER BY id DESC LIMIT 1
            """, (u_id,))
            last_tx = cursor.fetchone()
            balance = last_tx["balance_after"] if last_tx else 0

            cursor.execute("""
                SELECT COUNT(*) as tx_count
                FROM credit_transactions
                WHERE user_id = ?
            """, (u_id,))
            count_row = cursor.fetchone()
            tx_count = count_row["tx_count"] if count_row else 0

            users_data[tg_id] = {
                "user_id": u_id,
                "telegram_user_id": tg_id,
                "username": u["username"],
                "balance": balance,
                "tx_count": tx_count,
            }
    finally:
        conn.close()

    return users_data


def reconcile(backend_db_path: str, bot_db_path: str, verbose: bool = False) -> int:
    """
    Compares balances across databases.
    Returns 0 if all matching, 1 if discrepancies detected.
    """
    print("=" * 70)
    print(" AutoPress Read-Only Credit Balance Reconciliation")
    print("=" * 70)
    print(f"Backend DB: {os.path.abspath(backend_db_path)}")
    print(f"Bot DB:     {os.path.abspath(bot_db_path)}")
    print("-" * 70)

    try:
        backend_data = get_backend_balances(backend_db_path)
    except Exception as e:
        print(f"❌ Error reading backend DB: {e}")
        return 2

    try:
        bot_data = get_bot_balances(bot_db_path)
    except Exception as e:
        print(f"❌ Error reading bot DB: {e}")
        return 2

    all_tg_ids = sorted(set(backend_data.keys()).union(set(bot_data.keys())))
    if not all_tg_ids:
        print("ℹ️ No Telegram users found in either database.")
        return 0

    print(f"{'Telegram ID':<15} | {'Backend Bal':<12} | {'Bot Bal':<10} | {'Status':<10} | {'Details'}")
    print("-" * 70)

    matches = 0
    mismatches = 0
    backend_only = 0
    bot_only = 0

    for tg_id in all_tg_ids:
        b_info = backend_data.get(tg_id)
        bot_info = bot_data.get(tg_id)

        if b_info and bot_info:
            b_bal = b_info["balance"]
            bot_bal = bot_info["balance"]
            if b_bal == bot_bal:
                status = "✅ MATCH"
                matches += 1
                details = f"Balance: {b_bal}"
            else:
                status = "❌ MISMATCH"
                mismatches += 1
                diff = b_bal - bot_bal
                details = f"Diff: {diff:+d} (Backend: {b_bal}, Bot: {bot_bal})"
        elif b_info and not bot_info:
            b_bal = b_info["balance"]
            status = "⚠️ BACKEND"
            backend_only += 1
            details = f"Backend Bal: {b_bal} (Not present in bot DB)"
        else:
            bot_bal = bot_info["balance"] if bot_info else 0
            status = "⚠️ BOT ONLY"
            bot_only += 1
            details = f"Bot Bal: {bot_bal} (Not synced to backend DB)"

        if verbose or status != "✅ MATCH":
            print(f"{tg_id:<15} | {str(b_info['balance'] if b_info else 'N/A'):<12} | {str(bot_info['balance'] if bot_info else 'N/A'):<10} | {status:<10} | {details}")

    print("-" * 70)
    print(f"Summary: Total Users: {len(all_tg_ids)} | Matches: {matches} | Discrepancies: {mismatches} | Backend Only: {backend_only} | Bot Only: {bot_only}")
    print("=" * 70)

    if mismatches > 0:
        print("⚠️ ACTION RECOMMENDED: Discrepancies found. Run backend balance sync to align bot caches.")
        return 1

    print("✅ All balances are reconciled and consistent.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Reconcile AutoPress Telegram user credit balances across databases.")
    parser.add_argument(
        "--backend-db",
        default=os.environ.get("AUTOPRESS_BACKEND_DB", "AutoPress-backend/autopress.db"),
        help="Path to backend SQLite database (default: AutoPress-backend/autopress.db)"
    )
    parser.add_argument(
        "--bot-db",
        default=os.environ.get("AUTOPRESS_BOT_DB", "autopress-telegram-bot/autopress.db"),
        help="Path to user bot SQLite database (default: autopress-telegram-bot/autopress.db)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show all users including matching balances"
    )

    args = parser.parse_args()
    code = reconcile(args.backend_db, args.bot_db, verbose=args.verbose)
    sys.exit(code)


if __name__ == "__main__":
    main()

