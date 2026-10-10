"""
AutoPress Backend API Client

Acts as an HTTP client communicating directly with the existing AutoPress backend service.
Does NOT implement OCR, Gemini extraction, rembg, or PDF generation locally.
"""

from datetime import datetime, timezone, timedelta
import io
import json
from typing import Any, Dict, List, Optional, Tuple
import httpx
import jwt
from PIL import Image
from config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class AutoPressAPIClient:
    """HTTP Client for communicating with the existing AutoPress backend API."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.AUTOPRESS_API_URL).rstrip("/")

    def generate_auth_token(self, user_id: int = 1, role: str = "admin") -> str:
        """Generates a signed JWT access token compatible with AutoPress backend auth."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "email": "admin@autopress.com",
            "role": role,
            "iat": now,
            "exp": now + timedelta(days=7)
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

    async def check_health(self) -> bool:
        """Check if the AutoPress backend API is accessible."""
        url = f"{self.base_url}/health"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception as e:
            logger.warning("Backend health check failed: %s", e)
            return False

    async def process_pdf_template(
        self,
        pdf_bytes: bytes,
        filename: str = "fayda.pdf"
    ) -> Tuple[bool, Optional[bytes], Optional[str]]:
        """
        Sends a Fayda ID PDF to the existing AutoPress backend endpoint (/process-pdf-template).
        
        Returns:
            (success: bool, result_pdf_bytes: Optional[bytes], error_message: Optional[str])
        """
        url = f"{self.base_url}/process-pdf-template"
        token = self.generate_auth_token()
        headers = self._get_service_headers()
        headers["Accept"] = "image/png, application/pdf, application/json"

        files = {
            "pdf_1": (filename, pdf_bytes, "application/pdf")
        }

        logger.info("Submitting PDF to AutoPress backend: %s (size: %d bytes)", url, len(pdf_bytes))

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, headers=headers, files=files)

            if response.status_code == 200:
                result_bytes = response.content
                logger.info("Received lossless PNG sheet from AutoPress backend (%d bytes)", len(result_bytes))
                return True, result_bytes, None

            # Handle error responses from backend
            err_detail = "Processing failed on backend."
            try:
                data = response.json()
                err_detail = data.get("error") or data.get("message") or str(data)
            except Exception:
                err_detail = response.text[:200] if response.text else f"HTTP status {response.status_code}"

            logger.error("Backend returned error %d: %s", response.status_code, err_detail)
            return False, None, err_detail

        except httpx.TimeoutException:
            logger.error("AutoPress backend request timed out after 120 seconds.")
            return False, None, "Processing timed out. Please try again."
        except httpx.ConnectError:
            logger.error("Could not connect to AutoPress backend at %s", url)
            return False, None, "AutoPress backend service is currently unavailable."
        except Exception as e:
            logger.error("Unexpected error during backend request: %s", e)
            return False, None, f"Service error: {str(e)}"

    def _get_service_headers(self) -> Dict[str, str]:
        """Returns service authentication headers for machine-to-machine backend endpoints."""
        headers: Dict[str, str] = {}
        secret = (
            getattr(settings, "AUTOPRESS_SERVICE_SECRET", "") or
            getattr(settings, "AUTOPRESS_ADMIN_BOT_SECRET", "")
        )
        if secret:
            headers["X-Service-Secret"] = secret
            headers["X-Admin-Bot-Secret"] = secret
        token = self.generate_auth_token(role="admin")
        headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get_admin_headers(self) -> Dict[str, str]:
        """Returns authentication headers suitable for backend admin endpoints."""
        return self._get_service_headers()

    def get_telegram_balance_sync(self, telegram_user_id: int) -> Tuple[bool, int, Optional[str]]:
        """
        Synchronously fetches authoritative credit balance for a Telegram user.
        Fast timeout (2.5s) to avoid blocking Telegram command handlers.
        """
        url = f"{self.base_url}/api/user/telegram/{telegram_user_id}/balance"
        headers = self._get_service_headers()
        try:
            with httpx.Client(timeout=2.5) as client:
                resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return True, int(data.get("balance", 0)), None
            return False, 0, f"HTTP {resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            logger.debug("Failed to fetch balance sync from backend for user %s: %s", telegram_user_id, e)
            return False, 0, str(e)

    async def get_telegram_balance(self, telegram_user_id: int) -> Tuple[bool, int, Optional[str]]:
        """Asynchronously fetches authoritative credit balance for a Telegram user."""
        url = f"{self.base_url}/api/user/telegram/{telegram_user_id}/balance"
        headers = self._get_service_headers()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return True, int(data.get("balance", 0)), None
            return False, 0, f"HTTP {resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            logger.debug("Failed to fetch balance async from backend for user %s: %s", telegram_user_id, e)
            return False, 0, str(e)

    async def deduct_telegram_credit(
        self,
        telegram_user_id: int,
        amount: int = 1,
        reason: str = "Fayda PDF Processing",
        job_id: Optional[str] = None
    ) -> Tuple[bool, int, Optional[str]]:
        """Atomically deducts credits on the backend."""
        url = f"{self.base_url}/api/user/telegram/{telegram_user_id}/deduct"
        headers = self._get_service_headers()
        payload = {"amount": amount, "reason": reason, "job_id": job_id}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
            data = resp.json() if resp.status_code in (200, 400) else {}
            if resp.status_code == 200:
                return True, int(data.get("new_balance", 0)), None
            err = data.get("error") or f"HTTP {resp.status_code}"
            return False, int(data.get("current_balance", 0)), err
        except Exception as e:
            logger.debug("Backend credit deduction failed for user %s: %s", telegram_user_id, e)
            return False, 0, str(e)

    async def refund_telegram_credit(
        self,
        telegram_user_id: int,
        amount: int = 1,
        reason: str = "Processing failure refund",
        job_id: Optional[str] = None
    ) -> Tuple[bool, int, Optional[str]]:
        """Atomically refunds credits on the backend."""
        url = f"{self.base_url}/api/user/telegram/{telegram_user_id}/refund"
        headers = self._get_service_headers()
        payload = {"amount": amount, "reason": reason, "job_id": job_id}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
            data = resp.json() if resp.status_code in (200, 400) else {}
            if resp.status_code == 200:
                return True, int(data.get("new_balance", 0)), None
            err = data.get("error") or f"HTTP {resp.status_code}"
            return False, int(data.get("current_balance", 0)), err
        except Exception as e:
            logger.debug("Backend credit refund failed for user %s: %s", telegram_user_id, e)
            return False, 0, str(e)

    def submit_payment_sync(
        self,
        payment_id: str,
        telegram_user_id: int,
        telegram_username: Optional[str],
        package_id: str,
        credits_requested: int,
        amount_etb: float,
        payment_method: str,
        screenshot_file_id: Optional[str] = None,
        screenshot_url: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Synchronously records a pending payment request on the backend."""
        url = f"{self.base_url}/api/payments/telegram"
        headers = self._get_service_headers()
        payload = {
            "payment_id": payment_id,
            "telegram_user_id": telegram_user_id,
            "telegram_username": telegram_username or "",
            "package_id": package_id,
            "credits_requested": credits_requested,
            "amount_etb": amount_etb,
            "payment_method": payment_method,
            "screenshot_file_id": screenshot_file_id,
            "screenshot_url": screenshot_url
        }
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                return True, data.get("data"), None
            return False, None, f"HTTP {resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            logger.debug("Backend payment submission notice for %s: %s", payment_id, e)
            return False, None, str(e)

    async def approve_payment(
        self,
        payment_id: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], int, Optional[str]]:
        """Calls authoritative backend endpoint to approve payment and grant credits."""
        url = f"{self.base_url}/api/admin/payments/{payment_id}/approve"
        headers = self._get_admin_headers()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers)
            data = resp.json() if resp.status_code in (200, 400) else {}
            if resp.status_code == 200:
                return True, data.get("data"), int(data.get("new_balance", 0)), None
            err = data.get("error") or f"HTTP {resp.status_code}"
            current_bal = int(data.get("current_balance", 0))
            return False, data.get("data"), current_bal, err
        except Exception as e:
            logger.error("Backend payment approval error for %s: %s", payment_id, e)
            return False, None, 0, str(e)

    def approve_payment_sync(
        self,
        payment_id: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], int, Optional[str]]:
        """Synchronously calls authoritative backend endpoint to approve payment and grant credits."""
        url = f"{self.base_url}/api/admin/payments/{payment_id}/approve"
        headers = self._get_admin_headers()
        try:
            with httpx.Client(timeout=6.0) as client:
                resp = client.post(url, headers=headers)
            data = resp.json() if resp.status_code in (200, 400) else {}
            if resp.status_code == 200:
                return True, data.get("data"), int(data.get("new_balance", 0)), None
            err = data.get("error") or f"HTTP {resp.status_code}"
            current_bal = int(data.get("current_balance", 0))
            return False, data.get("data"), current_bal, err
        except Exception as e:
            logger.debug("Backend payment approval notice for %s: %s", payment_id, e)
            return False, None, 0, str(e)

    def reject_payment_sync(
        self,
        payment_id: str,
        reason: str = ""
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Synchronously calls authoritative backend endpoint to reject payment."""
        url = f"{self.base_url}/api/admin/payments/{payment_id}/reject"
        headers = self._get_admin_headers()
        payload = {"reason": reason}
        try:
            with httpx.Client(timeout=6.0) as client:
                resp = client.post(url, headers=headers, json=payload)
            data = resp.json() if resp.status_code in (200, 400) else {}
            if resp.status_code == 200:
                return True, data.get("data"), None
            err = data.get("error") or f"HTTP {resp.status_code}"
            return False, data.get("data"), err
        except Exception as e:
            logger.debug("Backend payment rejection notice for %s: %s", payment_id, e)
            return False, None, str(e)



autopress_api_client = AutoPressAPIClient()
