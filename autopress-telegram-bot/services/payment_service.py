"""
Payment Service

Business logic for payment requests, manual verification, and admin approval workflows.
"""

import uuid
from typing import Any, Dict, List, Optional, Tuple
from database.repositories.payment_repository import PaymentRepository
from config import CREDIT_PACKAGES
from utils.logger import setup_logger

logger = setup_logger(__name__)


class PaymentService:
    """Service layer managing user top-up payment requests."""

    @staticmethod
    def create_payment_request(
        telegram_user_id: int,
        package_id: str,
        payment_method: str,
        screenshot_file_id: Optional[str] = None,
        telegram_username: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate package and create a new PENDING payment request."""
        package = CREDIT_PACKAGES.get(package_id)
        if not package:
            raise ValueError(f"Invalid package_id: {package_id}")

        payment_id = f"pay_{uuid.uuid4().hex[:10]}"

        # Forward to authoritative backend API first
        from services.autopress_api import autopress_api_client
        api_ok, backend_data, err = autopress_api_client.submit_payment_sync(
            payment_id=payment_id,
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            package_id=package_id,
            credits_requested=package["credits"],
            amount_etb=float(package["price_etb"]),
            payment_method=payment_method,
            screenshot_file_id=screenshot_file_id
        )
        if not api_ok:
            logger.error("Backend payment submission failed for user %s: %s", telegram_user_id, err)
            raise RuntimeError(f"Backend payment submission failed: {err or 'Connection error'}")

        # Save locally in SQLite DB only after backend confirms
        payment = PaymentRepository.create_payment_request(
            payment_id=payment_id,
            telegram_user_id=telegram_user_id,
            package_id=package_id,
            credits_requested=package["credits"],
            amount_etb=float(package["price_etb"]),
            payment_method=payment_method,
            screenshot_file_id=screenshot_file_id
        )

        return payment

    @staticmethod
    def get_payment(payment_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a payment record by ID."""
        return PaymentRepository.get_payment(payment_id)

    @staticmethod
    def get_user_payments(telegram_user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent payment history for a specific user."""
        return PaymentRepository.get_user_payments(telegram_user_id, limit=limit)

    @staticmethod
    def get_pending_payments(limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve all unreviewed pending payment requests."""
        return PaymentRepository.get_pending_payments(limit=limit)

    @staticmethod
    def approve_payment(
        payment_id: str,
        admin_id: int
    ) -> Tuple[bool, str, Optional[Dict[str, Any]], int]:
        """Atomically approve payment and grant credits via authoritative backend."""
        from services.autopress_api import autopress_api_client
        api_ok, backend_payment, backend_bal, api_err = autopress_api_client.approve_payment_sync(payment_id)
        if not api_ok:
            logger.error("Backend payment approval failed for %s: %s", payment_id, api_err)
            return False, f"Backend approval failed: {api_err}", None, 0

        # Update local SQLite DB status without granting credits locally
        PaymentRepository.update_payment_status(
            payment_id=payment_id,
            status="APPROVED",
            admin_id=admin_id
        )
        local_payment = PaymentRepository.get_payment(payment_id)
        if local_payment:
            from database.repositories.credit_repository import CreditRepository
            CreditRepository.sync_balance_snapshot(local_payment["telegram_user_id"], backend_bal)

        return True, "Payment successfully approved.", backend_payment or local_payment, backend_bal

    @staticmethod
    def reject_payment(
        payment_id: str,
        admin_id: int,
        reason: str = ""
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Atomically reject payment via authoritative backend."""
        from services.autopress_api import autopress_api_client
        api_ok, backend_payment, api_err = autopress_api_client.reject_payment_sync(
            payment_id=payment_id,
            reason=reason
        )
        if not api_ok:
            logger.error("Backend payment rejection failed for %s: %s", payment_id, api_err)
            return False, f"Backend rejection failed: {api_err}", None

        PaymentRepository.update_payment_status(
            payment_id=payment_id,
            status="REJECTED",
            admin_id=admin_id,
            reason=reason
        )
        local_payment = PaymentRepository.get_payment(payment_id)
        return True, "Payment successfully rejected.", backend_payment or local_payment


payment_service = PaymentService()
