import os
import hmac
import jwt
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from functools import wraps
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from models import UserModel

JWT_SECRET = os.environ.get("JWT_SECRET", os.environ.get("SECRET_KEY", "autopress-jwt-secret-production-change-me"))
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_DAYS = int(os.environ.get("TOKEN_EXPIRY_DAYS", 7))

def hash_password(password: str) -> str:
    """Hashes password using secure algorithm."""
    return generate_password_hash(password, method="scrypt")

def check_password(password: str, password_hash: str) -> bool:
    """Verifies password against stored hash."""
    return check_password_hash(password_hash, password)

def create_access_token(user_id: int, email: str, role: str) -> str:
    """Generates a signed JWT access token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + timedelta(days=TOKEN_EXPIRY_DAYS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
        return None

from services.firebase_service import verify_token as verify_firebase_id_token

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@autopress.com").strip().lower()

def get_current_user_from_request() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Extracts Bearer token or dedicated admin bot service secret from request.
    Verifies X-Admin-Bot-Secret header FIRST using hmac.compare_digest.
    Verifies Firebase ID token for website clients.
    Falls back to legacy JWT token for seamless backward compatibility.
    Returns (user_dict, error_message).
    """
    # 0. Dedicated Telegram Admin Bot Secret Check
    admin_bot_secret = request.headers.get("X-Admin-Bot-Secret", "").strip()
    if admin_bot_secret:
        expected_secret = os.environ.get("AUTOPRESS_ADMIN_BOT_SECRET", "").strip()
        if not expected_secret:
            return None, "Admin bot authentication is not configured on the server."
        if not hmac.compare_digest(admin_bot_secret, expected_secret):
            return None, "Invalid admin bot secret."

        admin_user = UserModel.get_by_email(ADMIN_EMAIL)
        if not admin_user:
            admin_user = UserModel.create_or_sync_firebase_user(
                firebase_uid="admin_bot_service_uid",
                email=ADMIN_EMAIL,
                full_name="AutoPress Admin",
                role="admin"
            )
        elif admin_user.get("role") != "admin":
            from database import db_session
            with db_session() as conn:
                conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (admin_user["id"],))
            admin_user["role"] = "admin"
        return admin_user, None

    # Normal website / user authentication flow
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif request.cookies.get("access_token"):
        token = request.cookies.get("access_token")
    elif request.args.get("token"):
        token = request.args.get("token")

    if not token:
        return None, "Authentication required. Please provide a valid token."

    # Prevent non-JWT tokens from reaching Firebase verify_id_token
    # Valid Firebase ID tokens and HS256 JWTs are compact JWT strings with 3 dot-separated parts (2 dots)
    if token.count(".") != 2:
        return None, "Invalid token format. Expected JWT token."

    # 1. Primary: Verify Firebase ID Token
    fb_decoded, fb_err = verify_firebase_id_token(token)
    if fb_decoded:
        fb_uid = fb_decoded.get("uid") or fb_decoded.get("sub")
        fb_email = fb_decoded.get("email", "").strip().lower()
        is_verified = bool(fb_decoded.get("email_verified", False))
        display_name = fb_decoded.get("name") or fb_email.split("@")[0]

        if not fb_uid or not fb_email:
            return None, "Invalid Firebase token payload: missing UID or email."

        # Auto-promote configured admin email
        default_role = "admin" if (ADMIN_EMAIL and fb_email == ADMIN_EMAIL) else "user"

        user = UserModel.create_or_sync_firebase_user(
            firebase_uid=fb_uid,
            email=fb_email,
            full_name=display_name,
            is_verified=is_verified,
            role=default_role
        )

        if not user:
            return None, "Could not resolve or create user account for this Firebase ID."

        if user.get("status") == "suspended":
            return None, "Account is suspended. Please contact the administrator."

        UserModel.update_last_activity(user["id"])
        return user, None

    # 2. Secondary: Fallback to internal access token (for test suite or legacy sessions)
    payload = decode_access_token(token)
    if payload and payload.get("sub"):
        try:
            user_id = int(payload["sub"])
            user = UserModel.get_by_id(user_id)
            if user:
                if user.get("status") == "suspended":
                    return None, "Account is suspended. Please contact the administrator."
                UserModel.update_last_activity(user["id"])
                return user, None
        except (ValueError, TypeError):
            pass

    return None, fb_err or "Invalid or expired authentication token. Please log in again."

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user, error = get_current_user_from_request()
        if error or not user:
            return jsonify({"status": "error", "error": error or "Unauthorized"}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user, error = get_current_user_from_request()
        if error or not user:
            return jsonify({"status": "error", "error": error or "Unauthorized"}), 401
        if user.get("role") != "admin":
            return jsonify({"status": "error", "error": "Admin privileges required."}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function
