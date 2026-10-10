"""
Credits & Payment Keyboards

Builds keyboards for credit packages, payment methods, navigation,
and inline admin review actions.
"""

from typing import Dict, Any
from telegram import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from config import CREDIT_PACKAGES


def get_balance_keyboard() -> ReplyKeyboardMarkup:
    """Returns the keyboard shown on the Balance screen with a prominent Buy Credits button."""
    keyboard = [
        [KeyboardButton("🛒 Buy Credits"), KeyboardButton("💳 My Payments")],
        [KeyboardButton("📸 Upload / Process ID"), KeyboardButton("🏠 Back to Menu")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_packages_keyboard() -> ReplyKeyboardMarkup:
    """Returns the reply keyboard displaying available credit packages."""
    keyboard = [
        [KeyboardButton("10 Credits — 100 ETB"), KeyboardButton("20 Credits — 200 ETB")],
        [KeyboardButton("50 Credits — 500 ETB"), KeyboardButton("100 Credits — 1,000 ETB")],
        [KeyboardButton("⬅️ Back"), KeyboardButton("🏠 Back to Menu"), KeyboardButton("❌ Cancel")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_payment_methods_keyboard() -> ReplyKeyboardMarkup:
    """Returns the reply keyboard for choosing payment method (Bank or Telebirr)."""
    keyboard = [
        [KeyboardButton("🏦 Bank Account"), KeyboardButton("📱 Telebirr")],
        [KeyboardButton("⬅️ Back"), KeyboardButton("🏠 Back to Menu"), KeyboardButton("❌ Cancel")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_payment_waiting_keyboard() -> ReplyKeyboardMarkup:
    """Returns navigation keyboard while waiting for payment screenshot."""
    keyboard = [
        [KeyboardButton("⬅️ Back"), KeyboardButton("🏠 Back to Menu"), KeyboardButton("❌ Cancel")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_admin_review_keyboard(payment_id: str) -> InlineKeyboardMarkup:
    """Returns the inline review keyboard for admin approval/rejection."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_payment:{payment_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_payment:{payment_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
