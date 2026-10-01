from flask import Blueprint, request, jsonify, g
from models import UserModel, CreditLedgerModel, ProcessingRecordModel
from services.auth_service import login_required

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
