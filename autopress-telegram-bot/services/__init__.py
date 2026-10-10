"""
Services Package

Exports application business logic singletons.
"""

from services.user_service import user_service, UserService
from services.credit_service import credit_service, CreditService
from services.job_service import job_service, JobService
from services.payment_service import payment_service, PaymentService
from services.autopress_api import autopress_api_client, AutoPressAPIClient

__all__ = [
    "user_service",
    "UserService",
    "credit_service",
    "CreditService",
    "job_service",
    "JobService",
    "payment_service",
    "PaymentService",
    "autopress_api_client",
    "AutoPressAPIClient",
]
