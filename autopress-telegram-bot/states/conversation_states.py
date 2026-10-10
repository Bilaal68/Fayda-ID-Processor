"""
Conversation State Machine

Defines discrete conversation states for handling multi-step flows
such as batch uploading, credit top-up receipt submission, and settings.
"""

from enum import Enum, auto


class ConversationState(Enum):
    """Enumeration of possible conversation states for a Telegram user."""
    
    IDLE = auto()
    WAITING_FOR_PDF = auto()
    PROCESSING = auto()
    WAITING_FOR_PAYMENT = auto()
    WAITING_FOR_RECEIPT = auto()
    WAITING_FOR_PACKAGE_SELECTION = auto()
    WAITING_FOR_PAYMENT_METHOD = auto()
    WAITING_FOR_PAYMENT_SCREENSHOT = auto()
    SELECTING_LANGUAGE = auto()
