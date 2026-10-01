import os
import json
from typing import Optional, Dict, Any, Tuple
import firebase_admin
from firebase_admin import auth as fb_admin_auth, credentials
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "seer-95544").strip()
SERVICE_ACCOUNT_PATH = os.environ.get(
    "FIREBASE_SERVICE_ACCOUNT_PATH",
    os.path.join(BASE_DIR, "firebase-service-account.json")
).strip()

_firebase_initialized = False
_has_service_account = False
_auth_request = google_requests.Request()

def init_firebase() -> bool:
    """
    Initializes the Firebase Admin SDK safely.
    Supports either:
    1. Full service account JSON (via file path or env var).
    2. Project ID mode using Google's public x509 cert validation.
    """
    global _firebase_initialized, _has_service_account
    if _firebase_initialized:
        return True

    # Check if app already initialized
    try:
        firebase_admin.get_app()
        _firebase_initialized = True
        return True
    except ValueError:
        pass

    # 1. Try service account file if present and valid
    if os.path.exists(SERVICE_ACCOUNT_PATH) and os.path.getsize(SERVICE_ACCOUNT_PATH) > 10:
        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred, options={"projectId": PROJECT_ID})
            _firebase_initialized = True
            _has_service_account = True
            print("✅ Firebase Admin SDK initialized with Service Account Certificate.")
            return True
        except Exception as e:
            print(f"⚠️ Service account file present but failed to load: {e}")

    # 2. Try raw JSON environment variable if provided
    raw_sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw_sa_json.startswith("{") and raw_sa_json.endswith("}"):
        try:
            sa_dict = json.loads(raw_sa_json)
            cred = credentials.Certificate(sa_dict)
            firebase_admin.initialize_app(cred, options={"projectId": PROJECT_ID})
            _firebase_initialized = True
            _has_service_account = True
            print("✅ Firebase Admin SDK initialized with FIREBASE_SERVICE_ACCOUNT_JSON env.")
            return True
        except Exception as e:
            print(f"⚠️ FIREBASE_SERVICE_ACCOUNT_JSON parse error: {e}")

    # 3. Initialize default app with projectId
    try:
        firebase_admin.initialize_app(options={"projectId": PROJECT_ID})
        _firebase_initialized = True
        print(f"✅ Firebase initialized with Project ID: {PROJECT_ID}")
        return True
    except Exception as e:
        print(f"⚠️ Note: Firebase default app init notice: {e}")
        return False

# Initialize on module load
init_firebase()

def verify_token(token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Verifies a Firebase ID token.
    Returns: (decoded_token_dict, error_message)
    Decoded payload contains:
    - uid / sub: Firebase User ID
    - email: User's verified or unverified email
    - email_verified: Boolean
    - name: Display name (if set)
    """
    if not token or not isinstance(token, str):
        return None, "Authentication token is missing."

    token = token.strip()
    if not token:
        return None, "Authentication token is empty."

    # Method A: Try Firebase Admin SDK if service account is active
    if _has_service_account:
        try:
            decoded = fb_admin_auth.verify_id_token(token, check_revoked=False)
            return decoded, None
        except Exception as e:
            pass  # Fall through to Google public verification

    # Method B: Direct Google OAuth2 ID Token Verification for Firebase (uses Google's public x509 certs)
    try:
        decoded = google_id_token.verify_firebase_token(
            token,
            _auth_request,
            audience=PROJECT_ID
        )
        if decoded:
            # Ensure 'uid' key exists matching 'sub'
            if "sub" in decoded and "uid" not in decoded:
                decoded["uid"] = decoded["sub"]
            return decoded, None
    except Exception as err:
        return None, f"Invalid or expired Firebase ID token: {str(err)}"

    return None, "Invalid or expired Firebase ID token."
