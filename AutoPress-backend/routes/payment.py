"""
AutoPress Backend - Payment Submission Blueprint

Provides endpoints for creating payment top-up requests from Web and Telegram Bot clients.
"""

import os
from flask import Blueprint, request, jsonify, g
from models import PaymentModel, UserModel
from services.auth_service import get_current_user_from_request

payment_bp = Blueprint('payment', __name__, url_prefix='/api/payments')


@payment_bp.route('/telegram', methods=['POST'])
def submit_telegram_payment():
    """
    Endpoint for Telegram bot to record a user's pending payment request.
    """
    data = request.get_json(silent=True) or {}
    payment_id = data.get('payment_id')
    telegram_user_id = data.get('telegram_user_id')
    telegram_username = data.get('telegram_username', '')
    package_id = data.get('package_id', 'credits_10')
    credits_requested = int(data.get('credits_requested', 10))
    amount_etb = float(data.get('amount_etb', 100.0))
    payment_method = data.get('payment_method', 'Bank Account (CBE)')
    screenshot_file_id = data.get('screenshot_file_id')
    screenshot_url = data.get('screenshot_url')

    if not payment_id or not telegram_user_id:
        return jsonify({'status': 'error', 'error': 'Payment ID and Telegram User ID are required.'}), 400

    # Ensure user is provisioned in backend
    tg_user = UserModel.get_or_create_telegram_user(
        telegram_user_id=telegram_user_id,
        username=telegram_username
    )

    payment = PaymentModel.create(
        payment_id=payment_id,
        user_id=tg_user['id'] if tg_user else None,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        package_id=package_id,
        credits_requested=credits_requested,
        amount_etb=amount_etb,
        payment_method=payment_method,
        screenshot_file_id=screenshot_file_id,
        screenshot_url=screenshot_url
    )

    return jsonify({
        'status': 'success',
        'message': 'Payment request successfully submitted.',
        'data': payment
    }), 201
