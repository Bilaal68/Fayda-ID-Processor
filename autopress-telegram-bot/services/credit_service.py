"""
Credit Service

Business logic layer managing credit balances, transactions,
and concurrency safety for Telegram users.
"""

import asyncio
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from database.repositories.credit_repository import CreditRepository
from utils.logger import setup_logger

logger = setup_logger(__name__)

# User-level asyncio locks to serialize concurrent operations from the same Telegram user
_user_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


class CreditService:
    """Service layer managing user credits and ledger operations."""

    @staticmethod
    def get_balance(telegram_user_id: int) -> int:
        """Get the current credit balance for the user."""
        return CreditRepository.get_balance(telegram_user_id)

    @staticmethod
    async def deduct_credit(
        telegram_user_id: int,
        amount: int = 1,
        reason: str = "Fayda PDF Processing",
        job_id: Optional[str] = None
    ) -> Tuple[bool, str, int]:
        """
        Atomically deduct credits with concurrency protection.
        Returns (success, message, new_balance).
        """
        if amount <= 0:
            return False, "Deduction amount must be positive", CreditRepository.get_balance(telegram_user_id)

        lock = _user_locks[telegram_user_id]
        async with lock:
            # 1. Pre-check balance
            current_balance = CreditRepository.get_balance(telegram_user_id)
            if current_balance < amount:
                return False, f"Insufficient credits. You have {current_balance} credits.", current_balance

            # 2. Record negative delta transaction
            success, msg, new_bal = CreditRepository.record_transaction(
                telegram_user_id=telegram_user_id,
                amount=-amount,
                transaction_type="PROCESSING_DEDUCTION",
                reason=reason,
                job_id=job_id
            )
            return success, msg, new_bal

    @staticmethod
    async def refund_credit(
        telegram_user_id: int,
        amount: int = 1,
        reason: str = "Processing failure refund",
        job_id: Optional[str] = None
    ) -> Tuple[bool, str, int]:
        """
        Atomically refund credits to user.
        Returns (success, message, new_balance).
        """
        if amount <= 0:
            return False, "Refund amount must be positive", CreditRepository.get_balance(telegram_user_id)

        lock = _user_locks[telegram_user_id]
        async with lock:
            success, msg, new_bal = CreditRepository.record_transaction(
                telegram_user_id=telegram_user_id,
                amount=amount,
                transaction_type="PROCESSING_REFUND",
                reason=reason,
                job_id=job_id
            )
            return success, msg, new_bal

    @staticmethod
    def grant_credits(
        telegram_user_id: int,
        amount: int,
        reason: str = "Manual Admin Grant"
    ) -> Tuple[bool, str, int]:
        """Grant credits to a user."""
        return CreditRepository.record_transaction(
            telegram_user_id=telegram_user_id,
            amount=amount,
            transaction_type="ADMIN_GRANT",
            reason=reason
        )

    @staticmethod
    def get_history(telegram_user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent transaction history for user."""
        return CreditRepository.get_history(telegram_user_id, limit=limit)


credit_service = CreditService()
