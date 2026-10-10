"""
Administrator Authorization and Rate Limiting Service.

Ensures that only explicitly whitelisted numeric Telegram user IDs can access
administrative commands and interactive callbacks.
"""

import time
from functools import wraps
from typing import Callable, Any, Dict, Optional
from telegram import Update
from telegram.ext import ContextTypes
from config import settings, setup_logger

logger = setup_logger("admin_auth")

# Simple in-memory tracker for rate limiting sensitive actions per admin
_last_action_times: Dict[int, float] = {}
RATE_LIMIT_COOLDOWN_SECONDS = 0.5


def is_admin(user_id: Optional[int]) -> bool:
    """
    Verify whether the provided numeric Telegram user ID is authorized.
    Never trusts usernames; strictly checks against configured numeric IDs.
    """
    if user_id is None or not isinstance(user_id, int):
        return False
    return user_id in settings.ADMIN_TELEGRAM_IDS


def check_rate_limit(user_id: int, cooldown: float = RATE_LIMIT_COOLDOWN_SECONDS) -> bool:
    """
    Rate limiter for sensitive administrative actions.
    Returns True if allowed, False if the action was submitted too quickly.
    """
    now = time.monotonic()
    last = _last_action_times.get(user_id, 0.0)
    if now - last < cooldown:
        return False
    _last_action_times[user_id] = now
    return True


def admin_only(func: Callable) -> Callable:
    """
    Decorator for Telegram asynchronous handlers to enforce strict numeric admin authorization.
    Rejects any unauthorized user before handler execution.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        user = update.effective_user
        user_id = user.id if user else None

        if not is_admin(user_id):
            logger.warning(
                "Unauthorized administrative access attempted: user_id=%s, username=@%s",
                user_id,
                getattr(user, "username", "none")
            )

            denial_text = (
                "⛔ <b>Access Denied</b>\n\n"
                "You are not authorized to use the AutoPress Administration Bot."
            )

            if update.callback_query:
                try:
                    await update.callback_query.answer(
                        "⛔ Access denied: You are not an authorized administrator.",
                        show_alert=True
                    )
                except Exception:
                    pass
                try:
                    await update.callback_query.edit_message_text(
                        text=denial_text,
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            elif update.effective_message:
                try:
                    await update.effective_message.reply_text(
                        text=denial_text,
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            return None

        return await func(update, context, *args, **kwargs)

    return wrapper

