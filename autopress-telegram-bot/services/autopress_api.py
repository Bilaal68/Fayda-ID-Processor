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
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "image/png, application/pdf, application/json"
        }

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


autopress_api_client = AutoPressAPIClient()
