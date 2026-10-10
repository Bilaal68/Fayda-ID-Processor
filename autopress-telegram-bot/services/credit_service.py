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
    def get_authoritative_balance(telegram_user_id: int) -> Tuple[bool, int, Optional[str]]:
        """
        Fetches authoritative credit balance directly from the backend.
        Returns (success: bool, balance: int, error: Optional[str]).
        """
        try:
            from services.autopress_api import autopress_api_client
            api_ok, bal, err = autopress_api_client.get_telegram_balance_sync(telegram_user_id)
            if api_ok:
                CreditRepository.sync_balance_snapshot(telegram_user_id, bal)
                return True, bal, None
            return False, CreditRepository.get_balance(telegram_user_id), err
        except Exception as e:
            logger.debug("Backend balance lookup error for %s: %s", telegram_user_id, e)
            return False, CreditRepository.get_balance(telegram_user_id), str(e)

    @staticmethod
    def get_balance(telegram_user_id: int) -> int:
        """
        Get the credit balance for the user.
        Queries backend API first; on success, updates local snapshot and returns balance.
        Falls back to local SQLite ledger if backend is unreachable or disabled.
        """
        ok, bal, _ = CreditService.get_authoritative_balance(telegram_user_id)
        if ok:
            return bal
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
        Calls authoritative backend. Fails closed if backend deduction fails or cannot be reached.
        Does NOT fall back to local deduction.
        Returns (success, message, new_balance).
        """
        if amount <= 0:
            return False, "Deduction amount must be positive", CreditService.get_balance(telegram_user_id)

        lock = _user_locks[telegram_user_id]
        async with lock:
            try:
                from services.autopress_api import autopress_api_client
                api_ok, new_bal, err = await autopress_api_client.deduct_telegram_credit(
                    telegram_user_id=telegram_user_id,
                    amount=amount,
                    reason=reason,
                    job_id=job_id
                )
                if api_ok:
                    CreditRepository.sync_balance_snapshot(telegram_user_id, new_bal)
                    return True, "Success", new_bal
                elif err and "insufficient" in err.lower():
                    CreditRepository.sync_balance_snapshot(telegram_user_id, new_bal)
                    return False, f"Insufficient credits. You have {new_bal} credits.", new_bal
                else:
                    logger.error("Backend credit deduction failed for %s: %s", telegram_user_id, err)
                    current_balance = CreditRepository.get_balance(telegram_user_id)
                    return False, f"Credit deduction failed: {err or 'Server error'}. Please try again.", current_balance
            except Exception as e:
                logger.error("Backend deduction network/service failure for %s: %s", telegram_user_id, e)
                current_balance = CreditRepository.get_balance(telegram_user_id)
                return False, f"Unable to reach credit service: {e}. Please try again.", current_balance

    @staticmethod
    async def refund_credit(
        telegram_user_id: int,
        amount: int = 1,
        reason: str = "Processing failure refund",
        job_id: Optional[str] = None
    ) -> Tuple[bool, str, int]:
        """
        Atomically refund credits to user.
        Calls authoritative backend.
        Returns (success, message, new_balance).
        """
        if amount <= 0:
            return False, "Refund amount must be positive", CreditService.get_balance(telegram_user_id)

        lock = _user_locks[telegram_user_id]
        async with lock:
            try:
                from services.autopress_api import autopress_api_client
                api_ok, new_bal, err = await autopress_api_client.refund_telegram_credit(
                    telegram_user_id=telegram_user_id,
                    amount=amount,
                    reason=reason,
                    job_id=job_id
                )
                if api_ok:
                    CreditRepository.sync_balance_snapshot(telegram_user_id, new_bal)
                    return True, "Success", new_bal
                else:
                    logger.error("Backend refund failed for %s: %s", telegram_user_id, err)
                    return False, f"Backend refund failed: {err}", CreditRepository.get_balance(telegram_user_id)
            except Exception as e:
                logger.error("Backend refund exception for %s: %s", telegram_user_id, e)
                return False, f"Backend refund error: {e}", CreditRepository.get_balance(telegram_user_id)

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
