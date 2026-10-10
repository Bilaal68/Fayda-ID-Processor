"""
Job Service

Orchestrates PDF processing jobs, backend interaction, status updates,
and atomic credit deduction upon verified completion.
"""

import uuid
from typing import Any, Dict, List, Optional, Tuple
from database.repositories.job_repository import JobRepository
from services.credit_service import credit_service
from services.autopress_api import autopress_api_client
from utils.logger import setup_logger

logger = setup_logger(__name__)


class JobService:
    """Service layer orchestrating the lifecycle of print jobs."""

    @staticmethod
    async def process_pdf_upload(
        telegram_user_id: int,
        pdf_bytes: bytes,
        filename: str = "fayda.pdf"
    ) -> Tuple[bool, Optional[str], Optional[bytes], int]:
        """
        Executes the end-to-end PDF processing workflow:
        1. Checks current balance (rejects if 0).
        2. Creates a PENDING job record.
        3. Updates status to PROCESSING.
        4. Calls authoritative AutoPress backend API.
        5. On Success -> Deducts 1 credit atomically, marks COMPLETED, returns PDF bytes.
        6. On Failure -> Marks FAILED, does NOT deduct credit, returns error.

        Returns:
            (success: bool, error_code_or_msg: Optional[str], pdf_bytes: Optional[bytes], remaining_balance: int)
        """
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        ok, current_balance, err = credit_service.get_authoritative_balance(telegram_user_id)
        if not ok:
            logger.warning("Job creation aborted: Backend balance check failed for %s: %s", telegram_user_id, err)
            return False, "AUTHORITATIVE_BALANCE_UNAVAILABLE", None, current_balance

        # 1. Authoritative credit check
        if current_balance < 1:
            logger.warning("Job creation aborted: User %s has %d credits", telegram_user_id, current_balance)
            return False, "INSUFFICIENT_CREDITS", None, current_balance

        # 2. Register Job
        JobRepository.create_job(
            job_id=job_id,
            telegram_user_id=telegram_user_id,
            credit_cost=1,
            input_filename=filename
        )
        JobRepository.update_status(job_id, "PROCESSING")
        logger.info("Processing job %s for user %s started...", job_id, telegram_user_id)

        # 3. Call backend API
        backend_success, result_bytes, error_detail = await autopress_api_client.process_pdf_template(
            pdf_bytes=pdf_bytes,
            filename=filename
        )

        if not backend_success or not result_bytes:
            # Mark failed, preserve user credit
            JobRepository.update_status(job_id, "FAILED", error_detail or "Backend processing failed")
            logger.error("Job %s failed for user %s: %s", job_id, telegram_user_id, error_detail)
            return False, error_detail or "PROCESSING_FAILED", None, current_balance

        # 4. Processing succeeded -> Atomically deduct exactly 1 credit
        deduct_success, deduct_msg, new_balance = await credit_service.deduct_credit(
            telegram_user_id=telegram_user_id,
            amount=1,
            reason=f"Fayda PDF Processing (Job: {job_id})",
            job_id=job_id
        )

        if not deduct_success:
            logger.error("Failed to deduct credit for completed job %s: %s", job_id, deduct_msg)
            JobRepository.update_status(job_id, "COMPLETED_UNBILLED", deduct_msg)
            return False, "INSUFFICIENT_CREDITS", None, new_balance
        else:
            JobRepository.update_status(job_id, "COMPLETED")
            logger.info("Job %s successfully completed. New balance: %d", job_id, new_balance)

        return True, None, result_bytes, new_balance

    @staticmethod
    def get_user_jobs(telegram_user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch user's recent print jobs."""
        return JobRepository.get_user_jobs(telegram_user_id, limit=limit)


job_service = JobService()
