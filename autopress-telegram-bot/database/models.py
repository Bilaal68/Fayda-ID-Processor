"""
Database Models

Defines the database schema for the Telegram Bot service.
Telegram user identity is keyed on `telegram_user_id`.
"""

from datetime import datetime
from typing import Optional

# Scaffolding: Schema model definitions (User, CreditTransaction, PrintJob, PaymentReceipt)
# Models will track:
# - User: telegram_user_id, username, full_name, language, current_credits, is_active, created_at
# - CreditTransaction: id, telegram_user_id, amount, transaction_type, reason, created_at
# - PrintJob: id, telegram_user_id, slot_count, status, cost, output_file_id, created_at
# - PaymentReceipt: id, telegram_user_id, reference, amount, status, screenshot_file_id, created_at
