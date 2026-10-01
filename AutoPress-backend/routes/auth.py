from flask import Blueprint, request, jsonify, g
import re
from models import UserModel, CreditLedgerModel
from services.auth_service import (
    hash_password,
    check_password,
    create_access_token,
    login_required
)
from services.email_service import (
    generate_verification_token,
    verify_verification_token,
    generate_password_reset_token,
    verify_password_reset_token,
    send_verification_email,
    send_password_reset_email
)
from services.email_validator import validate_real_email

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not full_name:
        return jsonify({'status': 'error', 'error': 'Full name is required.'}), 400
    
    is_valid, err_msg = validate_real_email(email)
    if not is_valid:
        return jsonify({'status': 'error', 'error': err_msg}), 400
    if not password or len(password) < 6:
        return jsonify({'status': 'error', 'error': 'Password must be at least 6 characters long.'}), 400
    if password != confirm_password:
        return jsonify({'status': 'error', 'error': 'Passwords do not match.'}), 400

    existing_user = UserModel.get_by_email(email)
    if existing_user:
        return jsonify({'status': 'error', 'error': 'An account with this email already exists.'}), 409

    pwd_hash = hash_password(password)
    user = UserModel.create(
        email=email,
        password_hash=pwd_hash,
        full_name=full_name,
        role="user",
        is_verified=False
    )

    if not user:
        if UserModel.get_by_email(email):
            return jsonify({'status': 'error', 'error': 'An account with this email already exists.'}), 409
        return jsonify({'status': 'error', 'error': 'Failed to create account. Please try again.'}), 500


    token = generate_verification_token(email)
    send_verification_email(email, token)

    access_token = create_access_token(user['id'], user['email'], user['role'])

    return jsonify({
        'status': 'success',
        'message': 'Registration successful! Please check your email to verify your account.',
        'token': access_token,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role'],
            'status': user['status'],
            'is_verified': user['is_verified'],
            'current_credits': 0
        }
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'status': 'error', 'error': 'Email and password are required.'}), 400

    user_with_secret = None
    from database import db_session
    with db_session() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,))
        row = cursor.fetchone()
        if row:
            user_with_secret = dict(row)

    if not user_with_secret or not check_password(password, user_with_secret['password_hash']):
        return jsonify({'status': 'error', 'error': 'Invalid email or password.'}), 401

    if user_with_secret.get('status') == 'suspended':
        return jsonify({'status': 'error', 'error': 'Your account has been suspended. Please contact support.'}), 403

    UserModel.update_last_activity(user_with_secret['id'])
    balance = CreditLedgerModel.get_balance(user_with_secret['id'])
    access_token = create_access_token(user_with_secret['id'], user_with_secret['email'], user_with_secret['role'])

    return jsonify({
        'status': 'success',
        'message': 'Login successful.',
        'token': access_token,
        'user': {
            'id': user_with_secret['id'],
            'email': user_with_secret['email'],
            'full_name': user_with_secret['full_name'],
            'role': user_with_secret['role'],
            'status': user_with_secret['status'],
            'is_verified': bool(user_with_secret['is_verified']),
            'current_credits': balance
        }
    }), 200


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_me():
    user = g.current_user
    stats = CreditLedgerModel.get_user_stats(user['id'])
    return jsonify({
        'status': 'success',
        'user': {
            'id': user['id'],
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role'],
            'status': user['status'],
            'is_verified': bool(user.get('is_verified')),
            'firebase_uid': user.get('firebase_uid'),
            'current_credits': stats['current_credits'],
            'total_credits_received': stats['total_credits_received'],
            'total_credits_used': stats['total_credits_used']
        }
    }), 200


@auth_bp.route('/sync', methods=['POST', 'GET'])
@login_required
def sync_user():
    """
    Sync endpoint called immediately after Firebase client login/registration.
    The Firebase token in Authorization header has already verified & provisioned the user
    in get_current_user_from_request().
    """
    user = g.current_user
    data = request.get_json(silent=True) or {}
    updated_name = data.get('full_name', '').strip()
    if updated_name and updated_name != user.get('full_name'):
        from database import db_session
        with db_session() as conn:
            conn.execute("UPDATE users SET full_name = ? WHERE id = ?", (updated_name, user['id']))
        user = UserModel.get_by_id(user['id'])

    stats = CreditLedgerModel.get_user_stats(user['id'])
    return jsonify({
        'status': 'success',
        'message': 'User synced successfully.',
        'user': {
            'id': user['id'],
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role'],
            'status': user['status'],
            'is_verified': bool(user.get('is_verified')),
            'firebase_uid': user.get('firebase_uid'),
            'current_credits': stats['current_credits'],
            'total_credits_received': stats['total_credits_received'],
            'total_credits_used': stats['total_credits_used']
        }
    }), 200


@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    data = request.get_json(silent=True) or {}
    token = data.get('token', '').strip()
    if not token:
        return jsonify({'status': 'error', 'error': 'Verification token is required.'}), 400

    email = verify_verification_token(token)
    if not email:
        return jsonify({'status': 'error', 'error': 'Verification link has expired or is invalid.'}), 400

    user = UserModel.get_by_email(email)
    if not user:
        return jsonify({'status': 'error', 'error': 'User not found.'}), 404

    UserModel.update_verification(user['id'], True)
    return jsonify({
        'status': 'success',
        'message': 'Your email address has been successfully verified!'
    }), 200


@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'status': 'error', 'error': 'Email is required.'}), 400

    user = UserModel.get_by_email(email)
    if not user:
        return jsonify({'status': 'success', 'message': 'If an account exists, a verification link has been sent.'}), 200

    if user['is_verified']:
        return jsonify({'status': 'success', 'message': 'Account is already verified.'}), 200

    token = generate_verification_token(email)
    send_verification_email(email, token)
    return jsonify({'status': 'success', 'message': 'Verification email has been resent.'}), 200


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'status': 'error', 'error': 'Email is required.'}), 400

    user = UserModel.get_by_email(email)
    if user:
        token = generate_password_reset_token(email)
        send_password_reset_email(email, token)

    return jsonify({
        'status': 'success',
        'message': 'If an account exists with this email, password reset instructions have been sent.'
    }), 200


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get('token', '').strip()
    new_password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not token:
        return jsonify({'status': 'error', 'error': 'Reset token is required.'}), 400
    if not new_password or len(new_password) < 6:
        return jsonify({'status': 'error', 'error': 'Password must be at least 6 characters long.'}), 400
    if new_password != confirm_password:
        return jsonify({'status': 'error', 'error': 'Passwords do not match.'}), 400

    email = verify_password_reset_token(token)
    if not email:
        return jsonify({'status': 'error', 'error': 'Password reset token has expired or is invalid.'}), 400

    user = UserModel.get_by_email(email)
    if not user:
        return jsonify({'status': 'error', 'error': 'User not found.'}), 404

    pwd_hash = hash_password(new_password)
    UserModel.update_password(user['id'], pwd_hash)

    return jsonify({
        'status': 'success',
        'message': 'Password has been successfully reset! You can now log in with your new password.'
    }), 200
