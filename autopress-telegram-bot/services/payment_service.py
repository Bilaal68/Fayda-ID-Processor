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
        payment = PaymentRepository.create_payment_request(
            payment_id=payment_id,
            telegram_user_id=telegram_user_id,
            package_id=package_id,
            credits_requested=package["credits"],
            amount_etb=float(package["price_etb"]),
            payment_method=payment_method,
            screenshot_file_id=screenshot_file_id
        )

        # Sync with backend API
        try:
            import httpx
            from config import settings
            with httpx.Client(timeout=3.0) as client:
                client.post(
                    f"{settings.AUTOPRESS_API_URL}/api/payments/telegram",
                    json={
                        "payment_id": payment_id,
                        "telegram_user_id": telegram_user_id,
                        "telegram_username": telegram_username or "",
                        "package_id": package_id,
                        "credits_requested": package["credits"],
                        "amount_etb": float(package["price_etb"]),
                        "payment_method": payment_method,
                        "screenshot_file_id": screenshot_file_id
                    }
                )
        except Exception as e:
            logger.debug("Backend payment sync notice: %s", e)

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
        """Atomically approve payment and grant credits."""
        return PaymentRepository.approve_payment(payment_id=payment_id, admin_id=admin_id)

    @staticmethod
    def reject_payment(
        payment_id: str,
        admin_id: int
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Atomically reject payment."""
        return PaymentRepository.reject_payment(payment_id=payment_id, admin_id=admin_id)


payment_service = PaymentService()
