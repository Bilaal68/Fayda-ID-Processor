"""
Unit Tests for Backend API Client.

Validates authenticated HTTP calls, parameter passing, token handling,
error handling, and timeouts using mocked HTTP responses.
"""

import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from services.backend_client import BackendClient


class TestBackendClient(unittest.IsolatedAsyncioTestCase):
    """Test suite for BackendClient service."""

    def setUp(self):
        self.client = BackendClient(base_url="http://mock-backend:5000")
        self.client.bot_secret = "mock-admin-bot-secret-123"
        self.client._cached_token = None

    async def test_get_stats_success(self):
        """get_stats successfully retrieves statistics payload."""
        mock_stats = {
            "telegram_users": 25,
            "total_users": 60,
            "total_revenue_etb": 4500.0,
            "pending_payments": 2
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {"status": "success", "data": mock_stats}

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_resp
            ok, data, err = await self.client.get_stats()

        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(data["telegram_users"], 25)
        self.assertEqual(data["total_revenue_etb"], 4500.0)

    async def test_list_telegram_users_scoped_to_telegram(self):
        """list_telegram_users strictly includes source=telegram in query params."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {
            "status": "success",
            "users": [{"id": 85, "telegram_user_id": 888777666, "current_credits": 10}],
            "total": 1
        }

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_resp
            ok, data, err = await self.client.list_telegram_users(search="test", limit=5, offset=0)

        self.assertTrue(ok)
        mock_req.assert_called_once()
        sent_params = mock_req.call_args[1]["params"]
        self.assertEqual(sent_params["source"], "telegram", "Query must be scoped strictly to source=telegram")
        self.assertEqual(sent_params["search"], "test")
        self.assertEqual(sent_params["limit"], 5)
        self.assertEqual(sent_params["offset"], 0)

    async def test_adjust_credits_payload(self):
        """adjust_credits sends correct payload and parses response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {
            "status": "success",
            "user_id": 85,
            "new_balance": 15,
            "amount": 5
        }

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_resp
            ok, data, err = await self.client.adjust_credits(
                user_id=85,
                amount=5,
                action="add",
                reason="Manual bonus"
            )

        self.assertTrue(ok)
        self.assertIsNone(err)
        sent_json = mock_req.call_args[1]["json"]
        self.assertEqual(sent_json["user_id"], 85)
        self.assertEqual(sent_json["amount"], 5)
        self.assertEqual(sent_json["action"], "add")
        self.assertEqual(sent_json["reason"], "Manual bonus")

    async def test_approve_payment_success(self):
        """approve_payment calls approval endpoint with payment ID."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {
            "status": "success",
            "message": "Payment approved",
            "new_balance": 20,
            "credits_added": 10
        }

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_resp
            ok, data, err = await self.client.approve_payment("pay_abc123")

        self.assertTrue(ok)
        self.assertEqual(data["new_balance"], 20)
        self.assertIn("/api/admin/payments/pay_abc123/approve", mock_req.call_args[1]["url"])

    async def test_reject_payment_payload(self):
        """reject_payment sends rejection reason."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {
            "status": "success",
            "message": "Payment rejected"
        }

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_resp
            ok, data, err = await self.client.reject_payment("pay_abc123", reason="Invalid receipt")

        self.assertTrue(ok)
        sent_json = mock_req.call_args[1]["json"]
        self.assertEqual(sent_json["reason"], "Invalid receipt")

    async def test_backend_timeout_error_handling(self):
        """Client safely catches TimeoutException without crashing."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.TimeoutException("Timed out")
            ok, data, err = await self.client.get_stats()

        self.assertFalse(ok)
        self.assertIsNone(data)
        self.assertIn("timed out", err.lower())

    async def test_backend_connect_timeout_handling(self):
        """Client catches ConnectTimeout and returns specific connection error."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.ConnectTimeout("Connect timeout")
            ok, data, err = await self.client.get_stats()

        self.assertFalse(ok)
        self.assertIsNone(data)
        self.assertIn("connection timed out", err.lower())

    async def test_backend_read_timeout_handling(self):
        """Client catches ReadTimeout and returns specific read error."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.ReadTimeout("Read timeout")
            ok, data, err = await self.client.get_stats()

        self.assertFalse(ok)
        self.assertIsNone(data)
        self.assertIn("read timed out", err.lower())

    async def test_backend_connect_error_handling(self):
        """Client safely catches ConnectError when backend is down."""
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.ConnectError("Connection refused")
            ok, data, err = await self.client.get_stats()

    async def test_missing_credentials_fails_gracefully(self):
        """Client fails gracefully without sending empty token or Bearer None when no credentials configured."""
        self.client.bot_secret = None
        self.client._cached_token = None
        with patch.object(self.client, "_authenticate", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = False
            ok, data, err = await self.client.list_telegram_users()

        self.assertFalse(ok)
        self.assertEqual(data["users"], [])
        self.assertIn("Authentication required", err)

    async def test_authorized_service_token_headers(self):
        """Client includes dedicated X-Admin-Bot-Secret header and does not send Bearer None."""
        self.client.bot_secret = "my-secret-bot-token"
        headers = await self.client._get_auth_headers()
        self.assertEqual(headers["X-Admin-Bot-Secret"], "my-secret-bot-token")
        self.assertNotIn("Authorization", headers)
        self.assertNotIn("Bearer None", str(headers))


if __name__ == "__main__":
    unittest.main()

