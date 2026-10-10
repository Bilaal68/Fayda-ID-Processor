"""
Upload Keyboards

Keyboards displayed during document upload flow.
"""

from telegram import ReplyKeyboardMarkup, KeyboardButton


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Returns a keyboard with Back to Menu and Cancel buttons."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🏠 Back to Menu"), KeyboardButton("❌ Cancel")]],
        resize_keyboard=True
    )
