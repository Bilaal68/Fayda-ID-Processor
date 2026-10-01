import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Tuple
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from dotenv import load_dotenv

# Load .env so SMTP settings are always available
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'), override=False)

SECRET_KEY = os.environ.get("SECRET_KEY", "autopress-secret-key-production-change-me")
serializer = URLSafeTimedSerializer(SECRET_KEY)

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "no-reply@autopress.com")
APP_URL = os.environ.get("APP_URL", "http://localhost:5173")

def generate_verification_token(email: str) -> str:
    return serializer.dumps(email, salt="email-verification-salt")

def verify_verification_token(token: str, max_age_seconds: int = 86400) -> Optional[str]:
    """Verify email verification token (default 24h validity)."""
    try:
        email = serializer.loads(token, salt="email-verification-salt", max_age=max_age_seconds)
        return email
    except (SignatureExpired, BadTimeSignature, Exception):
        return None

def generate_password_reset_token(email: str) -> str:
    return serializer.dumps(email, salt="password-reset-salt")

def verify_password_reset_token(token: str, max_age_seconds: int = 3600) -> Optional[str]:
    """Verify password reset token (default 1h validity)."""
    try:
        email = serializer.loads(token, salt="password-reset-salt", max_age=max_age_seconds)
        return email
    except (SignatureExpired, BadTimeSignature, Exception):
        return None

def send_email(to_email: str, subject: str, text_content: str, html_content: Optional[str] = None) -> Tuple[bool, str]:
    """
    Sends an email using configured SMTP or logs cleanly to console.
    Returns (success: bool, info_message: str).
    """
    if not SMTP_HOST:
        print(f"\n📨 [EMAIL SIMULATED - NO SMTP CONFIG]")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body: {text_content}\n")
        return True, "Email logged to console (SMTP not configured)"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email

        part1 = MIMEText(text_content, "plain")
        msg.attach(part1)

        if html_content:
            part2 = MIMEText(html_content, "html")
            msg.attach(part2)

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
        server.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        server.quit()
        return True, "Email sent successfully"
    except Exception as e:
        print(f"⚠️ Failed to send email to {to_email}: {e}")
        return False, str(e)

def send_verification_email(to_email: str, token: str) -> Tuple[bool, str, str]:
    verify_url = f"{APP_URL}?verify_token={token}"
    subject = "Verify your AutoPress Account"
    body = (
        f"Welcome to AutoPress!\n\n"
        f"Please verify your email address by clicking the link below:\n"
        f"{verify_url}\n\n"
        f"Verification Token: {token}\n\n"
        f"This link expires in 24 hours."
    )
    html = f"""
    <div style="font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 30px; border-radius: 12px;">
        <h2 style="color: #6366f1;">Welcome to AutoPress!</h2>
        <p>Please click the button below to verify your email address:</p>
        <a href="{verify_url}" style="display: inline-block; background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 15px 0;">Verify My Account</a>
        <p style="font-size: 12px; color: #94a3b8;">Or use verification token: <code>{token}</code></p>
    </div>
    """
    success, msg = send_email(to_email, subject, body, html)
    return success, msg, token

def send_password_reset_email(to_email: str, token: str) -> Tuple[bool, str, str]:
    reset_url = f"{APP_URL}?reset_token={token}"
    subject = "AutoPress Password Reset Request"
    body = (
        f"You requested to reset your AutoPress password.\n\n"
        f"Click the link below to choose a new password:\n"
        f"{reset_url}\n\n"
        f"Reset Token: {token}\n\n"
        f"This link expires in 1 hour. If you did not request this, please ignore this email."
    )
    html = f"""
    <div style="font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 30px; border-radius: 12px;">
        <h2 style="color: #6366f1;">AutoPress Password Reset</h2>
        <p>You requested a password reset. Click the button below:</p>
        <a href="{reset_url}" style="display: inline-block; background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 15px 0;">Reset Password</a>
        <p style="font-size: 12px; color: #94a3b8;">Or use reset token: <code>{token}</code></p>
    </div>
    """
    success, msg = send_email(to_email, subject, body, html)
    return success, msg, token
