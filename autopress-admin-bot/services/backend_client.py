"""
Backend API Client Service.

Provides authenticated asynchronous HTTP communication with the AutoPress Flask backend.
Encapsulates token management, request timeouts, error handling, and structured logging.
"""

from typing import Any, Dict, Optional, Tuple
import httpx
from config import settings, setup_logger

logger = setup_logger("backend_client")


class BackendClient:
    """Async client interacting with existing AutoPress administrative REST endpoints."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.BACKEND_BASE_URL).rstrip("/")
        self.timeout = httpx.Timeout(12.0, connect=5.0)
        self.bot_secret: Optional[str] = (
            settings.AUTOPRESS_ADMIN_BOT_SECRET or
            settings.BACKEND_SERVICE_TOKEN or
            None
        )
        self._cached_token: Optional[str] = None

    async def _get_auth_headers(self) -> Dict[str, str]:
        """Obtain valid headers using dedicated X-Admin-Bot-Secret or cached JWT token."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        if self.bot_secret:
            headers["X-Admin-Bot-Secret"] = self.bot_secret
            return headers

        if not self._cached_token:
            await self._authenticate()
        if self._cached_token:
            headers["Authorization"] = f"Bearer {self._cached_token}"
        return headers

    async def _authenticate(self) -> bool:
        """Authenticate with backend using configured admin credentials."""
        login_url = f"{self.base_url}/api/auth/login"
        payload = {
            "email": settings.ADMIN_EMAIL,
            "password": settings.ADMIN_PASSWORD
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(login_url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    token = data.get("token")
                    if token:
                        self._cached_token = token
                        logger.info("Successfully authenticated backend admin session for %s", settings.ADMIN_EMAIL)
                        return True
                logger.error("Backend admin login failed with status %d: %s", resp.status_code, resp.text)
                return False
        except Exception as exc:
            logger.error("Exception occurred while authenticating with backend: %s", str(exc))
            return False

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        retry_on_401: bool = True
    ) -> Tuple[bool, Any, Optional[str]]:
        """
        Execute an authenticated request with timeout and automatic 401 token refresh.
        Returns: (success: bool, data: Any, error_message: Optional[str])
        """
        headers = await self._get_auth_headers()
        if "X-Admin-Bot-Secret" not in headers and "Authorization" not in headers:
            logger.warning("No authentication credentials available for backend request.")
            return False, None, "Authentication required: No valid admin bot secret or login credentials configured."
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data
                )

                # If unauthorized and retry is permitted, refresh token and try once more
                if resp.status_code == 401 and retry_on_401 and not self.bot_secret:
                    logger.warning("Received 401 from backend. Attempting token refresh...")
                    refreshed = await self._authenticate()
                    if refreshed:
                        return await self._request(
                            method=method,
                            path=path,
                            params=params,
                            json_data=json_data,
                            retry_on_401=False
                        )

                if resp.is_success:
                    try:
                        return True, resp.json(), None
                    except Exception:
                        return True, resp.text, None

                # Handle expected error status codes
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("error") or err_json.get("message") or f"HTTP {resp.status_code}"
                except Exception:
                    err_msg = f"HTTP {resp.status_code}: {resp.text[:120]}"

                logger.warning("Backend request failed [%s %s]: status=%d, error=%s", method, path, resp.status_code, err_msg)
                return False, None, err_msg

        except httpx.ConnectError:
            err = "Unable to connect to AutoPress backend service. Please verify the service is running."
            logger.error("Connection error for %s", url)
            return False, None, err
        except httpx.TimeoutException:
            err = "AutoPress backend request timed out. Please try again."
            logger.error("Timeout connecting to %s", url)
            return False, None, err
        except Exception as exc:
            err = f"Unexpected backend communication error: {str(exc)}"
            logger.error("Unexpected error for %s: %s", url, str(exc))
            return False, None, err

    # --------------------------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------------------------
    async def get_stats(self) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Fetch system-wide statistics from /api/admin/stats."""
        ok, res, err = await self._request("GET", "/api/admin/stats")
        if ok and isinstance(res, dict) and "data" in res:
            return True, res["data"], None
        return ok, res, err

    # --------------------------------------------------------------------------
    # TELEGRAM USERS (Scoped strictly to Telegram bot users)
    # --------------------------------------------------------------------------
    async def list_telegram_users(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 6,
        offset: int = 0
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        List registered Telegram bot users via /api/admin/users?source=telegram.
        """
        params: Dict[str, Any] = {
            "source": "telegram",
            "limit": limit,
            "offset": offset
        }
        if search:
            params["search"] = search
        if status:
            params["status"] = status

        ok, res, err = await self._request("GET", "/api/admin/users", params=params)
        if ok and isinstance(res, dict):
            return True, res, None
        return False, {"users": [], "total": 0, "counts": {}}, err

    async def get_user_detail(self, user_id: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Fetch detailed information for a user via /api/admin/users/{user_id}."""
        ok, res, err = await self._request("GET", f"/api/admin/users/{user_id}")
        if ok and isinstance(res, dict) and "data" in res:
            return True, res["data"], None
        return ok, res, err

    # --------------------------------------------------------------------------
    # CREDIT MANAGEMENT
    # --------------------------------------------------------------------------
    async def adjust_credits(
        self,
        user_id: int,
        amount: int,
        action: str,
        reason: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Atomically adjust user credits via /api/admin/credits.
        action must be 'add' or 'remove'.
        """
        payload = {
            "user_id": user_id,
            "amount": amount,
            "action": action,
            "reason": reason
        }
        ok, res, err = await self._request("POST", "/api/admin/credits", json_data=payload)
        return ok, res, err

    # --------------------------------------------------------------------------
    # PAYMENTS & REVIEWS
    # --------------------------------------------------------------------------
    async def list_payments(
        self,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 6,
        offset: int = 0
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """List top-up payments via /api/admin/payments."""
        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset
        }
        if status:
            params["status"] = status
        if search:
            params["search"] = search

        ok, res, err = await self._request("GET", "/api/admin/payments", params=params)
        if ok and isinstance(res, dict):
            return True, res, None
        return False, {"payments": [], "total": 0, "counts": {}}, err

    async def get_payment_detail(self, payment_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Fetch payment details via /api/admin/payments/{payment_id}."""
        ok, res, err = await self._request("GET", f"/api/admin/payments/{payment_id}")
        if ok and isinstance(res, dict) and "data" in res:
            return True, res["data"], None
        return ok, res, err

    async def approve_payment(self, payment_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Atomically approve payment via /api/admin/payments/{payment_id}/approve."""
        ok, res, err = await self._request("POST", f"/api/admin/payments/{payment_id}/approve")
        return ok, res, err

    async def reject_payment(
        self,
        payment_id: str,
        reason: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Atomically reject payment via /api/admin/payments/{payment_id}/reject."""
        payload = {"reason": reason}
        ok, res, err = await self._request("POST", f"/api/admin/payments/{payment_id}/reject", json_data=payload)
        return ok, res, err

    async def get_payment_receipt_bytes(
        self,
        payment_id: str
    ) -> Tuple[bool, Optional[bytes], Optional[str], Optional[str]]:
        """
        Fetch receipt image bytes via /api/admin/payments/{payment_id}/receipt.
        Returns: (success, image_bytes, content_type, error)
        """
        url = f"{self.base_url}/api/admin/payments/{payment_id}/receipt"
        headers = await self._get_auth_headers()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    ctype = resp.headers.get("content-type", "image/jpeg")
                    return True, resp.content, ctype, None
                return False, None, None, f"Receipt not found (HTTP {resp.status_code})"
        except Exception as exc:
            return False, None, None, str(exc)

    # --------------------------------------------------------------------------
    # TRANSACTION LEDGER & PROCESSING JOBS
    # --------------------------------------------------------------------------
    async def get_credit_history(
        self,
        user_id: Optional[int] = None,
        limit: int = 6,
        offset: int = 0
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Fetch global credit transactions via /api/admin/credits/history."""
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if user_id:
            params["user_id"] = user_id
        ok, res, err = await self._request("GET", "/api/admin/credits/history", params=params)
        if ok and isinstance(res, dict):
            return True, res, None
        return False, {"history": [], "total": 0}, err

    async def get_processing_history(
        self,
        user_id: Optional[int] = None,
        limit: int = 6,
        offset: int = 0
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Fetch document processing history via /api/admin/processing/history."""
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if user_id:
            params["user_id"] = user_id
        ok, res, err = await self._request("GET", "/api/admin/processing/history", params=params)
        if ok and isinstance(res, dict):
            return True, res, None
        return False, {"history": [], "total": 0}, err


# Default backend client instance
backend_client = BackendClient()

