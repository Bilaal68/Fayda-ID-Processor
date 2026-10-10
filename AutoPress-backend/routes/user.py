from flask import Blueprint, request, jsonify, g
from models import UserModel, CreditLedgerModel, ProcessingRecordModel
from services.auth_service import login_required, service_secret_required

user_bp = Blueprint('user', __name__, url_prefix='/api/user')

@user_bp.route('/dashboard', methods=['GET'])
@login_required
def get_dashboard():
    user = g.current_user
    user_id = user['id']

    credit_stats = CreditLedgerModel.get_user_stats(user_id)
    doc_stats = ProcessingRecordModel.get_stats(user_id)
    recent_transactions, _ = CreditLedgerModel.get_history(user_id=user_id, limit=10, offset=0)
    recent_processing, _ = ProcessingRecordModel.get_history(user_id=user_id, limit=10, offset=0)

    return jsonify({
        'status': 'success',
        'data': {
            'user': {
                'id': user['id'],
                'full_name': user['full_name'],
                'email': user['email'],
                'role': user['role'],
                'status': user['status'],
                'is_verified': user['is_verified'],
                'created_at': user['created_at'],
                'last_activity': user['last_activity']
            },
            'credits': {
                'current_balance': credit_stats['current_credits'],
                'total_received': credit_stats['total_credits_received'],
                'total_used': credit_stats['total_credits_used']
            },
            'processing': {
                'total_documents': doc_stats['total_documents'],
                'successful_documents': doc_stats['successful_documents'],
                'failed_documents': doc_stats['failed_documents']
            },
            'recent_activity': {
                'transactions': recent_transactions,
                'processing': recent_processing
            }
        }
    }), 200


@user_bp.route('/credits/history', methods=['GET'])
@login_required
def get_credit_history():
    user = g.current_user
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = max(int(request.args.get('offset', 0)), 0)

    history, total = CreditLedgerModel.get_history(user_id=user['id'], limit=limit, offset=offset)

    return jsonify({
        'status': 'success',
        'history': history,
        'total': total,
        'limit': limit,
        'offset': offset,
        'current_balance': CreditLedgerModel.get_balance(user['id'])
    }), 200


@user_bp.route('/processing/history', methods=['GET'])
@login_required
def get_processing_history():
    user = g.current_user
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = max(int(request.args.get('offset', 0)), 0)

    history, total = ProcessingRecordModel.get_history(user_id=user['id'], limit=limit, offset=offset)

    return jsonify({
        'status': 'success',
        'history': history,
        'total': total,
        'limit': limit,
        'offset': offset
    }), 200


@user_bp.route('/telegram/sync', methods=['POST'])
@service_secret_required
def sync_telegram_user():
    """
    Sync endpoint called when a Telegram user starts or interacts with the bot.
    Idempotently ensures the Telegram user exists and is up to date in the central backend.
    """
    data = request.get_json(silent=True) or {}
    telegram_user_id = data.get('telegram_user_id')
    username = data.get('username', '')
    first_name = data.get('first_name', '')
    last_name = data.get('last_name', '')
    full_name = data.get('full_name', '')

    if not telegram_user_id:
        return jsonify({'status': 'error', 'error': 'telegram_user_id is required.'}), 400

    try:
        tg_id = int(telegram_user_id)
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'error': 'telegram_user_id must be a numeric integer.'}), 400

    user = UserModel.get_or_create_telegram_user(
        telegram_user_id=tg_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name
    )

    current_balance = CreditLedgerModel.get_balance(user['id'])

    return jsonify({
        'status': 'success',
        'message': 'Telegram user synchronized successfully.',
        'user': user,
        'current_balance': current_balance
    }), 200


@user_bp.route('/telegram/<int:telegram_user_id>/balance', methods=['GET'])
@service_secret_required
def get_telegram_user_balance(telegram_user_id: int):
    """
    Authoritative balance endpoint for a Telegram user.
    Auto-provisions the user if not yet seen, and returns current balance.
    """
    if not telegram_user_id:
        return jsonify({'status': 'error', 'error': 'Invalid telegram_user_id.'}), 400

    user = UserModel.get_or_create_telegram_user(telegram_user_id=telegram_user_id)
    current_balance = CreditLedgerModel.get_balance(user['id'])

    return jsonify({
        'status': 'success',
        'telegram_user_id': telegram_user_id,
        'user_id': user['id'],
        'balance': current_balance
    }), 200


@user_bp.route('/telegram/<int:telegram_user_id>/deduct', methods=['POST'])
@service_secret_required
def deduct_telegram_user_credit(telegram_user_id: int):
    """
    Atomically deducts credits from a Telegram user's authoritative balance.
    Ensures idempotency when job_id is provided.
    """
    if not telegram_user_id:
        return jsonify({'status': 'error', 'error': 'Invalid telegram_user_id.'}), 400

    data = request.get_json(silent=True) or {}
    amount = data.get('amount', 1)
    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'error': 'amount must be a positive integer.'}), 400

    reason = data.get('reason', 'Fayda PDF Processing')
    job_id = data.get('job_id')

    user = UserModel.get_or_create_telegram_user(telegram_user_id=telegram_user_id)
    success, message, new_balance = CreditLedgerModel.record_transaction(
        user_id=user['id'],
        amount=-amount,
        transaction_type='PROCESSING_DEDUCTION',
        reason=reason,
        job_id=job_id
    )

    if not success:
        return jsonify({
            'status': 'error',
            'error': message,
            'telegram_user_id': telegram_user_id,
            'current_balance': new_balance
        }), 400

    return jsonify({
        'status': 'success',
        'message': message,
        'telegram_user_id': telegram_user_id,
        'user_id': user['id'],
        'new_balance': new_balance,
        'deducted': amount
    }), 200


@user_bp.route('/telegram/<int:telegram_user_id>/refund', methods=['POST'])
@service_secret_required
def refund_telegram_user_credit(telegram_user_id: int):
    """
    Atomically refunds credits to a Telegram user's authoritative balance.
    Ensures idempotency when job_id is provided.
    """
    if not telegram_user_id:
        return jsonify({'status': 'error', 'error': 'Invalid telegram_user_id.'}), 400

    data = request.get_json(silent=True) or {}
    amount = data.get('amount', 1)
    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'error': 'amount must be a positive integer.'}), 400

    reason = data.get('reason', 'Processing failure refund')
    job_id = data.get('job_id')

    user = UserModel.get_or_create_telegram_user(telegram_user_id=telegram_user_id)
    success, message, new_balance = CreditLedgerModel.record_transaction(
        user_id=user['id'],
        amount=amount,
        transaction_type='PROCESSING_REFUND',
        reason=reason,
        job_id=job_id
    )

    if not success:
        return jsonify({
            'status': 'error',
            'error': message,
            'telegram_user_id': telegram_user_id,
            'current_balance': new_balance
        }), 400

    return jsonify({
        'status': 'success',
        'message': message,
        'telegram_user_id': telegram_user_id,
        'user_id': user['id'],
        'new_balance': new_balance,
        'refunded': amount
    }), 200
