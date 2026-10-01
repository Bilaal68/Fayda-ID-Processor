import os
import json
from services.auth_service import get_current_user_from_request
from models import UserModel

# ============================================================
# FIREBASE INIT — OPTIONAL / LEGACY
# ============================================================
db = None  # Placeholder for legacy code; AutoPress uses SQLite WAL ledger

# ============================================================
# AUTHENTICATION
# ============================================================

def verify_token(request, require_verified: bool = True):
    """
    Verifies Bearer JWT token from request.
    Returns authenticated user ID. Raises Exception if missing, invalid, suspended,
    or (by default) email not yet verified.
    """
    user, error = get_current_user_from_request()
    if error or not user:
        raise Exception(error or "Authentication required. Please log in.")
    if require_verified and not user.get("is_verified"):
        raise Exception("EMAIL_NOT_VERIFIED: Please verify your email address before processing documents.")
    return user["id"]

def get_current_user(request):
    """Returns the full authenticated user dictionary."""
    user, error = get_current_user_from_request()
    if error or not user:
        raise Exception(error or "Authentication required. Please log in.")
    return user