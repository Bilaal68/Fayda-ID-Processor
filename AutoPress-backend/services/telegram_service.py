"""
AutoPress Backend - Telegram Integration Service

Handles sending notifications to Telegram users upon payment approval/rejection,
and safely fetching payment receipts via Telegram Bot API for admin review.
"""

import os
import io
import logging
from typing import Optional, Tuple
import requests

logger = logging.getLogger(__name__)


def get_telegram_bot_token() -> str:
    """Retrieve configured Telegram bot token from environment."""
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _dispatch_telegram_message(telegram_user_id: int, message: str, bot_token: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": telegram_user_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("Successfully sent Telegram notification to user %s", telegram_user_id)
        else:
            logger.warning("Telegram notification to %s returned %d: %s", telegram_user_id, response.status_code, response.text)
    except Exception as e:
        logger.warning("Telegram notification error for user %s: %s", telegram_user_id, e)


def send_telegram_notification(telegram_user_id: int, message: str) -> bool:
    """
    Asynchronously sends a Markdown-formatted message to a Telegram user.
    Runs non-blocking in background thread so approval response is instant.
    """
    bot_token = get_telegram_bot_token()
    if not bot_token or not telegram_user_id:
        logger.warning("Cannot send Telegram notification: missing bot token or user ID (%s)", telegram_user_id)
        return False

    import threading
    threading.Thread(
        target=_dispatch_telegram_message,
        args=(telegram_user_id, message, bot_token),
        daemon=True
    ).start()
    return True


def fetch_telegram_receipt_image(file_id: str) -> Tuple[Optional[bytes], str]:
    """
    Safely retrieves a receipt image from Telegram by file_id.
    Returns: (image_bytes, mime_type)
    """
    bot_token = get_telegram_bot_token()
    if not bot_token or not file_id:
        return None, "image/jpeg"

    try:
        # 1. Get file path
        get_file_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        resp = requests.get(get_file_url, timeout=10)
        if resp.status_code != 200:
            logger.warning("Telegram getFile returned status %d: %s", resp.status_code, resp.text)
            return None, "image/jpeg"

        file_info = resp.json()
        file_path = file_info.get("result", {}).get("file_path")
        if not file_path:
            return None, "image/jpeg"

        # 2. Download file content
        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        dl_resp = requests.get(download_url, timeout=20)
        if dl_resp.status_code == 200:
            content_type = dl_resp.headers.get("Content-Type", "image/jpeg")
            if file_path.lower().endswith(".png"):
                content_type = "image/png"
            elif file_path.lower().endswith((".jpg", ".jpeg")):
                content_type = "image/jpeg"
            return dl_resp.content, content_type

    except Exception as e:
        logger.error("Failed to fetch Telegram receipt image for file_id %s: %s", file_id, e)

    return None, "image/jpeg"
