import os
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

def get_current_user_from_request() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Extracts Bearer token from Authorization header or cookie, verifies user in DB.
    Returns (user_dict, error_message).
    """
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

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        return None, "Invalid or expired authentication token. Please log in again."

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        return None, "Invalid user identifier in token."

    user = UserModel.get_by_id(user_id)
    if not user:
        return None, "User account not found."

    if user.get("status") == "suspended":
        return None, "Account is suspended. Please contact the administrator."

    # Update last activity timestamp
    UserModel.update_last_activity(user["id"])
    return user, None

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
