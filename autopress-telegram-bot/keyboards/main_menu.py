"""
Main Menu Keyboards

Builds navigation keyboards for the primary bot dashboard.
"""

from telegram import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns the persistent main menu reply keyboard."""
    keyboard = [
        [KeyboardButton("📸 Upload / Process ID"), KeyboardButton("💳 Balance")],
        [KeyboardButton("🛒 Buy Credits"), KeyboardButton("📋 My Jobs")],
        [KeyboardButton("👤 My Profile"), KeyboardButton("🌐 Language")],
        [KeyboardButton("ℹ️ Help"), KeyboardButton("❌ Cancel")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
