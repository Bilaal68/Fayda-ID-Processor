"""
Message Formatting & Localization Helpers

Provides templated user messages and localization resolver.
"""

from typing import Any, Dict
from locales import am, en

LOCALES: Dict[str, Any] = {
    "en": en,
    "am": am,
}


def get_text(key: str, lang: str = "am", **kwargs) -> str:
    """Retrieve localized message string by key with parameter formatting."""
    locale = LOCALES.get(lang, am)
    messages = getattr(locale, "MESSAGES", {})
    text = messages.get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text
