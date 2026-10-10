"""
Common Keyboards
"""

from telegram import ReplyKeyboardMarkup, KeyboardButton


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Returns standard navigation keyboard with Back to Menu and Cancel buttons."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🏠 Back to Menu"), KeyboardButton("❌ Cancel")]],
        resize_keyboard=True
    )
