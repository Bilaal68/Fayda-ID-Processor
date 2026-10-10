from flask import Blueprint, request, jsonify, g
from models import UserModel, CreditLedgerModel, ProcessingRecordModel, AdminStatsModel, PaymentModel
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
    # Sync any newly registered Firebase users into SQLite
    try:
        from services.firebase_service import fb_admin_auth
        fb_page = fb_admin_auth.list_users(max_results=100)
        for fu in fb_page.users:
            if fu.email:
                UserModel.create_or_sync_firebase_user(
                    firebase_uid=fu.uid,
                    email=fu.email,
                    full_name=fu.display_name or fu.email.split('@')[0],
                    is_verified=bool(fu.email_verified),
                    role="user"
                )
    except Exception:
        pass

    search = request.args.get('search', '').strip() or None
    source = request.args.get('source', '').strip() or None
    status = request.args.get('status', '').strip() or None
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = max(int(request.args.get('offset', 0)), 0)

    users, total, counts = UserModel.list_users(search=search, source=source, status=status, limit=limit, offset=offset)

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
        'counts': counts,
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


@admin_bp.route('/users/<int:user_id>/role', methods=['PATCH', 'POST'])
@admin_required
def update_user_role(user_id: int):
    data = request.get_json(silent=True) or {}
    new_role = data.get('role', '').strip().lower()

    if new_role not in ('user', 'admin'):
        return jsonify({'status': 'error', 'error': 'Role must be either "user" or "admin".'}), 400

    user = UserModel.get_by_id(user_id)
    if not user:
        return jsonify({'status': 'error', 'error': 'User not found.'}), 404

    # Prevent current admin from demoting themselves
    if user['id'] == g.current_user['id'] and new_role != 'admin':
        return jsonify({'status': 'error', 'error': 'You cannot demote your own active admin account.'}), 400

    success = UserModel.update_role(user_id, new_role)
    if not success:
        return jsonify({'status': 'error', 'error': 'Failed to update user role.'}), 500

    return jsonify({
        'status': 'success',
        'message': f'User role successfully updated to {new_role}.',
        'user_id': user_id,
        'email': user['email'],
        'new_role': new_role
    }), 200


@admin_bp.route('/users/promote-email', methods=['POST'])
@admin_required
def promote_user_by_email():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    new_role = data.get('role', 'admin').strip().lower()

    if not email:
        return jsonify({'status': 'error', 'error': 'Email is required.'}), 400

    if new_role not in ('user', 'admin'):
        return jsonify({'status': 'error', 'error': 'Role must be either "user" or "admin".'}), 400

    user = UserModel.get_by_email(email)
    if not user:
        # Check if registered in Firebase Auth and provision directly
        try:
            from services.firebase_service import fb_admin_auth
            fb_user = fb_admin_auth.get_user_by_email(email)
            if fb_user:
                user = UserModel.create_or_sync_firebase_user(
                    firebase_uid=fb_user.uid,
                    email=fb_user.email,
                    full_name=fb_user.display_name or fb_user.email.split('@')[0],
                    is_verified=bool(fb_user.email_verified),
                    role=new_role
                )
        except Exception:
            pass

    if not user:
        return jsonify({'status': 'error', 'error': f'No account found with email "{email}". Please make sure they register first.'}), 404

    if user['id'] == g.current_user['id'] and new_role != 'admin':
        return jsonify({'status': 'error', 'error': 'You cannot demote your own active admin account.'}), 400

    success = UserModel.update_role(user['id'], new_role)
    if not success:
        return jsonify({'status': 'error', 'error': 'Failed to update role.'}), 500

    return jsonify({
        'status': 'success',
        'message': f'Successfully upgraded {user["email"]} to {new_role}.',
        'user_id': user['id'],
        'email': user['email'],
        'new_role': new_role
    }), 200


@admin_bp.route('/credits', methods=['POST'])
@admin_required
def manage_credits():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    raw_amount = data.get('amount')
    action = data.get('action', 'add').strip().lower()
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
        reason = "Manual admin credit allocation" if action == 'add' else "Admin credit adjustment"

    user = UserModel.get_by_id(user_id)
    if not user:
        return jsonify({'status': 'error', 'error': 'Target user not found.'}), 404

    admin_id = g.current_user['id']
    admin_email = g.current_user['email']
    previous_balance = CreditLedgerModel.get_balance(user_id)

    if action == 'add':
        delta = amount
        tx_type = 'ADMIN_MANUAL_CREDIT'
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

    # If user has a linked Telegram ID and credits were added, dispatch notification
    if action == 'add' and user.get('telegram_user_id'):
        from services.telegram_service import send_telegram_notification
        user_tg_msg = (
            "🎁 *Credits Added*\n\n"
            f"*{amount} credits* have been added to your AutoPress account.\n\n"
            f"💰 *Previous balance:* {previous_balance}\n"
            f"➕ *Added:* +{amount}\n"
            f"💳 *New balance:* {new_balance} credits\n\n"
            f"Reason: {reason}"
        )
        send_telegram_notification(user['telegram_user_id'], user_tg_msg)

    target_name = user['full_name'] or user['email'] or f"Telegram User {user.get('telegram_user_id')}"
    return jsonify({
        'status': 'success',
        'message': f'Successfully added {amount} credits to {target_name}. New balance: {new_balance}.',
        'user_id': user_id,
        'action': action,
        'amount': amount,
        'previous_balance': previous_balance,
        'new_balance': new_balance,
        'balance_after': new_balance,
        'transaction_type': tx_type
    }), 200


@admin_bp.route('/users/<int:user_id>/add-credits', methods=['POST'])
@admin_required
def add_credits_to_user(user_id: int):
    """Direct alias for manual admin credit grant to a specific user."""
    data = request.get_json(silent=True) or {}
    raw_amount = data.get('amount')
    reason = data.get('reason', '').strip() or "Manual admin credit"

    try:
        amount = int(raw_amount)
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'error': 'Amount must be a positive integer.'}), 400

    user = UserModel.get_by_id(user_id)
    if not user:
        return jsonify({'status': 'error', 'error': 'Target user not found.'}), 404

    admin_id = g.current_user['id']
    previous_balance = CreditLedgerModel.get_balance(user_id)

    success, message, new_balance = CreditLedgerModel.record_transaction(
        user_id=user_id,
        amount=amount,
        transaction_type='ADMIN_MANUAL_CREDIT',
        reason=reason,
        admin_id=admin_id
    )

    if not success:
        return jsonify({'status': 'error', 'error': message}), 400

    # Telegram user notification
    if user.get('telegram_user_id'):
        from services.telegram_service import send_telegram_notification
        user_tg_msg = (
            "🎁 *Credits Added*\n\n"
            f"*{amount} credits* have been added to your AutoPress account.\n\n"
            f"💰 *Previous balance:* {previous_balance}\n"
            f"➕ *Added:* +{amount}\n"
            f"💳 *New balance:* {new_balance} credits\n\n"
            f"Reason: {reason}"
        )
        send_telegram_notification(user['telegram_user_id'], user_tg_msg)

    target_name = user['full_name'] or user['email'] or f"Telegram User {user.get('telegram_user_id')}"
    return jsonify({
        'status': 'success',
        'message': f'Successfully granted +{amount} credits to {target_name}.',
        'user_id': user_id,
        'credits_added': amount,
        'previous_balance': previous_balance,
        'new_balance': new_balance,
        'balance_after': new_balance
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


# ===========================================================================
# PAYMENT TOP-UP MANAGEMENT (TELEGRAM & WEB TOP-UPS)
# ===========================================================================

@admin_bp.route('/payments', methods=['GET'])
@admin_required
def list_admin_payments():
    status = request.args.get('status', '').strip() or None
    search = request.args.get('search', '').strip() or None
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = max(int(request.args.get('offset', 0)), 0)

    payments, total, counts = PaymentModel.list_payments(
        status=status,
        search=search,
        limit=limit,
        offset=offset
    )

    return jsonify({
        'status': 'success',
        'payments': payments,
        'total': total,
        'counts': counts,
        'limit': limit,
        'offset': offset
    }), 200


@admin_bp.route('/payments/<string:payment_id>', methods=['GET'])
@admin_required
def get_admin_payment_detail(payment_id: str):
    payment = PaymentModel.get_by_id(payment_id)
    if not payment:
        return jsonify({'status': 'error', 'error': 'Payment request not found.'}), 404

    # Fetch user details and credit balance if available
    user_balance = None
    if payment.get('user_id'):
        user_balance = CreditLedgerModel.get_balance(payment['user_id'])

    return jsonify({
        'status': 'success',
        'data': payment,
        'user_balance': user_balance
    }), 200


@admin_bp.route('/payments/<string:payment_id>/receipt', methods=['GET'])
@admin_required
def get_admin_payment_receipt(payment_id: str):
    """
    Secure receipt image endpoint.
    Only accessible to authorized administrators.
    Fetches receipt from Telegram or local storage and streams image bytes.
    """
    payment = PaymentModel.get_by_id(payment_id)
    if not payment:
        return jsonify({'status': 'error', 'error': 'Payment request not found.'}), 404

    file_id = payment.get('screenshot_file_id')
    file_url = payment.get('screenshot_url')

    if not file_id and not file_url:
        return jsonify({'status': 'error', 'error': 'No receipt image uploaded for this payment.'}), 404

    from flask import Response
    from services.telegram_service import fetch_telegram_receipt_image

    if file_id:
        img_bytes, mime_type = fetch_telegram_receipt_image(file_id)
        if img_bytes:
            return Response(img_bytes, mimetype=mime_type)

    # Fallback to local file path if stored locally
    if file_url and os.path.exists(file_url):
        try:
            with open(file_url, 'rb') as f:
                content = f.read()
            mime = 'image/png' if file_url.endswith('.png') else 'image/jpeg'
            return Response(content, mimetype=mime)
        except Exception:
            pass

    return jsonify({'status': 'error', 'error': 'Receipt image could not be loaded from storage.'}), 404


@admin_bp.route('/payments/<string:payment_id>/approve', methods=['POST'])
@admin_required
def approve_admin_payment(payment_id: str):
    """
    Atomically approves a PENDING payment request and grants credits.
    Guarantees strict idempotency and audit trail.
    """
    admin_id = g.current_user['id']
    admin_email = g.current_user['email']

    success, message, payment_data, new_balance = PaymentModel.approve_payment(
        payment_id=payment_id,
        admin_id=admin_id,
        admin_email=admin_email
    )

    if not success:
        return jsonify({
            'status': 'error',
            'error': message,
            'data': payment_data,
            'current_balance': new_balance
        }), 400

    return jsonify({
        'status': 'success',
        'message': message,
        'data': payment_data,
        'new_balance': new_balance,
        'credits_added': payment_data['credits_requested']
    }), 200


@admin_bp.route('/payments/<string:payment_id>/reject', methods=['POST'])
@admin_required
def reject_admin_payment(payment_id: str):
    """
    Atomically marks a PENDING payment request as REJECTED.
    Credits remain 0.
    """
    admin_id = g.current_user['id']
    admin_email = g.current_user['email']
    data = request.get_json(silent=True) or {}
    reason = data.get('reason', '').strip()

    success, message, payment_data = PaymentModel.reject_payment(
        payment_id=payment_id,
        admin_id=admin_id,
        admin_email=admin_email,
        reason=reason
    )

    if not success:
        return jsonify({
            'status': 'error',
            'error': message,
            'data': payment_data
        }), 400

    return jsonify({
        'status': 'success',
        'message': message,
        'data': payment_data
    }), 200
