from flask import Blueprint, request, jsonify, g
from models import UserModel, CreditLedgerModel, ProcessingRecordModel, AdminStatsModel
from services.auth_service import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@admin_bp.route('/stats', methods=['GET'])
@admin_required
def get_stats():
    stats = AdminStatsModel.get_overview_stats()
    return jsonify({
        'status': 'success',
        'data': stats
    }), 200


@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    search = request.args.get('search', '').strip() or None
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = max(int(request.args.get('offset', 0)), 0)

    users, total = UserModel.list_users(search=search, limit=limit, offset=offset)

    enriched = []
    for u in users:
        uid = u['id']
        balance = CreditLedgerModel.get_balance(uid)
        doc_stats = ProcessingRecordModel.get_stats(uid)
        u_copy = dict(u)
        u_copy['current_credits'] = balance
        u_copy['total_documents'] = doc_stats['total_documents']
        u_copy['successful_documents'] = doc_stats['successful_documents']
        enriched.append(u_copy)

    return jsonify({
        'status': 'success',
        'users': enriched,
        'total': total,
        'limit': limit,
        'offset': offset
    }), 200


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user_detail(user_id: int):
    user = UserModel.get_by_id(user_id)
    if not user:
        return jsonify({'status': 'error', 'error': 'User not found.'}), 404

    credit_stats = CreditLedgerModel.get_user_stats(user_id)
    doc_stats = ProcessingRecordModel.get_stats(user_id)
    transactions, _ = CreditLedgerModel.get_history(user_id=user_id, limit=20, offset=0)
    processing, _ = ProcessingRecordModel.get_history(user_id=user_id, limit=20, offset=0)

    return jsonify({
        'status': 'success',
        'data': {
            'user': user,
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
            'recent_transactions': transactions,
            'recent_processing': processing
        }
    }), 200


@admin_bp.route('/users/<int:user_id>/status', methods=['PATCH'])
@admin_required
def update_user_status(user_id: int):
    data = request.get_json(silent=True) or {}
    new_status = data.get('status', '').strip().lower()

    if new_status not in ('active', 'suspended'):
        return jsonify({'status': 'error', 'error': 'Status must be either "active" or "suspended".'}), 400

    user = UserModel.get_by_id(user_id)
    if not user:
        return jsonify({'status': 'error', 'error': 'User not found.'}), 404

    if user['role'] == 'admin' and new_status == 'suspended':
        return jsonify({'status': 'error', 'error': 'Admin accounts cannot be suspended.'}), 400

    success = UserModel.update_status(user_id, new_status)
    if not success:
        return jsonify({'status': 'error', 'error': 'Failed to update user status.'}), 500

    return jsonify({
        'status': 'success',
        'message': f'User status successfully updated to {new_status}.',
        'user_id': user_id,
        'new_status': new_status
    }), 200


@admin_bp.route('/credits', methods=['POST'])
@admin_required
def manage_credits():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    raw_amount = data.get('amount')
    action = data.get('action', '').strip().lower()
    reason = data.get('reason', '').strip()

    if not user_id:
        return jsonify({'status': 'error', 'error': 'User ID is required.'}), 400

    try:
        amount = int(raw_amount)
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'error': 'Amount must be a positive integer.'}), 400

    if action not in ('add', 'remove'):
        return jsonify({'status': 'error', 'error': 'Action must be "add" or "remove".'}), 400

    if not reason:
        return jsonify({'status': 'error', 'error': 'A reason must be provided for credit adjustments.'}), 400

    user = UserModel.get_by_id(user_id)
    if not user:
        return jsonify({'status': 'error', 'error': 'Target user not found.'}), 404

    admin_id = g.current_user['id']
    if action == 'add':
        delta = amount
        tx_type = 'ADMIN_GRANT'
    else:
        delta = -amount
        tx_type = 'ADMIN_REMOVE'

    success, message, new_balance = CreditLedgerModel.record_transaction(
        user_id=user_id,
        amount=delta,
        transaction_type=tx_type,
        reason=reason,
        admin_id=admin_id
    )

    if not success:
        return jsonify({'status': 'error', 'error': message}), 400

    return jsonify({
        'status': 'success',
        'message': f'Successfully updated credits for {user["email"]}.',
        'user_id': user_id,
        'action': action,
        'amount': amount,
        'new_balance': new_balance
    }), 200


@admin_bp.route('/credits/history', methods=['GET'])
@admin_required
def get_global_credit_history():
    user_id = request.args.get('user_id', type=int)
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = max(int(request.args.get('offset', 0)), 0)

    history, total = CreditLedgerModel.get_history(user_id=user_id, limit=limit, offset=offset)

    return jsonify({
        'status': 'success',
        'history': history,
        'total': total,
        'limit': limit,
        'offset': offset
    }), 200


@admin_bp.route('/processing/history', methods=['GET'])
@admin_required
def get_global_processing_history():
    user_id = request.args.get('user_id', type=int)
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = max(int(request.args.get('offset', 0)), 0)

    history, total = ProcessingRecordModel.get_history(user_id=user_id, limit=limit, offset=offset)

    return jsonify({
        'status': 'success',
        'history': history,
        'total': total,
        'limit': limit,
        'offset': offset
    }), 200
