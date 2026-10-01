from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from routes.fayda import fayda_bp
from routes.auth import auth_bp
from routes.user import user_bp
from routes.admin import admin_bp
from database import init_db
from models import UserModel, CreditLedgerModel
from services.auth_service import hash_password
import os

# Initialize database schema
init_db()

# Bootstrap initial administrator account if none exists
def bootstrap_admin():
    try:
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@autopress.com").strip().lower()
        admin_password = os.environ.get("ADMIN_PASSWORD", "Admin123456!").strip()
        existing_admin = UserModel.get_by_email(admin_email)
        if not existing_admin:
            admin_user = UserModel.create(
                email=admin_email,
                password_hash=hash_password(admin_password),
                full_name="System Administrator",
                role="admin",
                is_verified=True
            )
            if admin_user:
                CreditLedgerModel.record_transaction(
                    user_id=admin_user["id"],
                    amount=1000,
                    transaction_type="ADMIN_GRANT",
                    reason="Initial system administrator allocation",
                    admin_id=admin_user["id"]
                )
                print(f"✅ Initial admin account provisioned: {admin_email}")
    except Exception as e:
        print(f"⚠️ Admin bootstrap notice: {e}")

bootstrap_admin()

app = Flask(__name__, static_folder='static')

# ============================================================
# CORS CONFIGURATION
# ============================================================
CORS(app, resources={
    r"/*": {
        "origins": [
            "https://auto-press-printer-shop-automation.vercel.app",
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:5000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5000",
            "null",
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        "allow_headers": [
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "Accept",
        ],
        "supports_credentials": True,
    }
})

# ============================================================
# REGISTER BLUEPRINTS
# ============================================================
app.register_blueprint(fayda_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(user_bp)
app.register_blueprint(admin_bp)


# ============================================================
# FORCE CORS HEADERS ON EVERY RESPONSE
# ============================================================
@app.after_request
def add_cors_headers(response):
    try:
        from flask import request as flask_request
        request_origin = flask_request.headers.get('Origin', '')
    except Exception:
        request_origin = ''

    if request_origin:
        response.headers['Access-Control-Allow-Origin'] = request_origin
    else:
        response.headers['Access-Control-Allow-Origin'] = '*'

    response.headers['Access-Control-Allow-Headers']     = 'Content-Type, Authorization, X-Requested-With, Accept'
    response.headers['Access-Control-Allow-Methods']     = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Max-Age']           = '3600'
    return response


# ============================================================
# HANDLE OPTIONS PREFLIGHT
# ============================================================
@app.before_request
def handle_preflight():
    from flask import request
    if request.method == 'OPTIONS':
        from flask import make_response
        response = make_response()
        response.headers['Access-Control-Allow-Origin']      = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Headers']     = 'Content-Type, Authorization, X-Requested-With, Accept'
        response.headers['Access-Control-Allow-Methods']     = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age']           = '3600'
        return response, 200

# ============================================================
# STATIC FILES
# ============================================================
@app.route('/static/previews/<path:filename>')
def serve_wedding_preview(filename):
    previews_path = os.path.join('static', 'previews')
    return send_from_directory(previews_path, filename)

# ============================================================
# HEALTH CHECK
# ============================================================
@app.route('/')
def index():
    return jsonify({
        'status':  'ok',
        'message': 'AutoPress API is running!'

    })

@app.route('/health')
def health_check():
    return jsonify({
        'status':  'healthy',
        'message': 'Backend is running smoothly!'
    })

# ============================================================
# DEBUG
# ============================================================
@app.route('/debug-info', methods=['GET'])
def debug_info():
    import sys
    from services.gemini import MODELS_TO_TRY
    return jsonify({
        'status':         'ok',
        'python_version': sys.version,
        'models':         MODELS_TO_TRY,
        'cors_enabled':   True,
        'env_vars': {
            'GEMINI_API_KEY_1':    'SET' if os.environ.get('GEMINI_API_KEY_1') else 'NOT SET',
            'REPLICATE_API_TOKEN': 'SET' if os.environ.get('REPLICATE_API_TOKEN') else 'NOT SET',
        }
    })

@app.route('/debug-test', methods=['GET'])
def debug_test():
    return jsonify({
        'status':  'ok',
        'message': 'Server is running with CORS enabled',

    })

# ============================================================
# RUN
# ============================================================
vercel_app = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
    app.run(debug=True, host='0.0.0.0', port=port)