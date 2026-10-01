from flask import Blueprint, request, jsonify, send_file
from fb.admin import verify_token, db
from models import UserModel, CreditLedgerModel, ProcessingRecordModel
from services.gemini import extract_from_images, extract_from_pdf
from services.pdf_generator import generate_final_pdf, generate_final_png
from datetime import datetime, timezone
import io
import os
import traceback
import uuid

os.environ['CUDA_VISIBLE_DEVICES']  = ''   # disable GPU search
if os.path.isdir('/app/models'):
    os.environ['U2NET_HOME'] = '/app/models'
os.environ['CUDA_VISIBLE_DEVICES']  = ''
os.environ['ORT_LOGGING_LEVEL']     = '3'

fayda_bp = Blueprint('fayda', __name__)

# ── Credit cost per template ──
CREDIT_COST_PER_DOCUMENT = int(os.environ.get("CREDIT_COST_PER_DOCUMENT", 1))
CREDIT_COST = {
    1: 1 * CREDIT_COST_PER_DOCUMENT,
    2: 2 * CREDIT_COST_PER_DOCUMENT,
    3: 3 * CREDIT_COST_PER_DOCUMENT,
    4: 4 * CREDIT_COST_PER_DOCUMENT,
    5: 5 * CREDIT_COST_PER_DOCUMENT,
}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _resolve_user_id(user_identifier):
    if isinstance(user_identifier, int):
        return user_identifier
    if isinstance(user_identifier, str):
        if user_identifier.isdigit():
            return int(user_identifier)
        u = UserModel.get_by_email(user_identifier)
        if u:
            return u['id']
    return None

def get_user_credits(user_id):
    uid = _resolve_user_id(user_id)
    if not uid:
        return 0
    return CreditLedgerModel.get_balance(uid)

def deduct_credits(user_id, amount, reason="Processing document", processing_id=None):
    """
    Atomically deducts or refunds credits.
    Positive amount = deduction (-amount).
    Negative amount = refund (+abs(amount)).
    """
    uid = _resolve_user_id(user_id)
    if not uid:
        return False, "User not found"

    if amount > 0:
        tx_type = "PROCESSING_DEDUCTION"
        delta = -amount
    else:
        tx_type = "PROCESSING_REFUND"
        delta = abs(amount)

    success, message, new_balance = CreditLedgerModel.record_transaction(
        user_id=uid,
        amount=delta,
        transaction_type=tx_type,
        reason=reason,
        processing_id=processing_id
    )
    if not success:
        return False, message
    return True, new_balance

def is_admin(user_id):
    """Check if user has admin role"""
    uid = _resolve_user_id(user_id)
    if not uid:
        return False
    user = UserModel.get_by_id(uid)
    return bool(user and user.get('role') == 'admin')


# ============================================================
# ENDPOINT 1 — Extract Image Data (WITH DETAILED LOGGING)
# ============================================================

@fayda_bp.route('/extract-image-data', methods=['POST'])
def extract_image_data():
    print("=" * 60)
    print("📸 EXTRACT IMAGE DATA ENDPOINT CALLED")
    print("=" * 60)
    
    try:
        # Step 1: Verify Firebase token
        try:
            email = verify_token(request)
            print(f"✅ User verified: {email}")
        except Exception as e:
            err_msg = str(e)
            print(f"❌ Token verification failed: {err_msg}")
            if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
                return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
            return jsonify({'error': err_msg}), 401

        # Step 2: Validate uploaded files
        if 'front_image' not in request.files:
            print("❌ front_image missing")
            return jsonify({'error': 'front_image is required'}), 400
        if 'back_image' not in request.files:
            print("❌ back_image missing")
            return jsonify({'error': 'back_image is required'}), 400
        if 'photo_qr_image' not in request.files:
            print("❌ photo_qr_image missing")
            return jsonify({'error': 'photo_qr_image is required'}), 400

        front = request.files['front_image']
        back = request.files['back_image']
        photo_qr = request.files['photo_qr_image']
        
        print(f"📁 Files received:")
        print(f"   - front: {front.filename} ({front.mimetype})")
        print(f"   - back: {back.filename} ({back.mimetype})")
        print(f"   - photo_qr: {photo_qr.filename} ({photo_qr.mimetype})")
        
        # Check file sizes
        front.seek(0, 2)
        front_size = front.tell()
        front.seek(0)
        back.seek(0, 2)
        back_size = back.tell()
        back.seek(0)
        photo_qr.seek(0, 2)
        photo_size = photo_qr.tell()
        photo_qr.seek(0)
        
        print(f"📏 File sizes: front={front_size} bytes, back={back_size} bytes, photo={photo_size} bytes")

        # Step 3: Validate file types
        allowed = {'image/jpeg', 'image/png', 'image/jpg', 'image/webp'}
        for f in [front, back, photo_qr]:
            if f.mimetype not in allowed:
                print(f"❌ Invalid file type: {f.mimetype}")
                return jsonify({'error': f'Invalid file type: {f.mimetype}'}), 400

        # Step 4: Run Gemini AI extraction
        print("🤖 Calling Gemini extraction...")
        try:
            extracted_texts, profile_b64, qr_b64 = extract_from_images(
                front, back, photo_qr
            )
            print("✅ Extraction successful")
            print(f"📝 Extracted fields: {list(extracted_texts.keys())}")
        except Exception as e:
            print(f"❌ Extraction failed: {str(e)}")
            print(traceback.format_exc())
            return jsonify({'error': f'Error extracting data: {str(e)}'}), 500

        # Step 5: Return extracted data + images
        return jsonify({
            'status': 'extracted',
            'data': {
                'extracted_texts': extracted_texts,
                'profile_image': profile_b64,
                'qr_image': qr_b64
            }
        }), 200
        
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

# ============================================================
# ENDPOINT 2 — Generate Final ID (direct, no queue) WITH CREDIT DEDUCTION
# ============================================================

@fayda_bp.route('/generate-final-id', methods=['POST'])
def generate_final_id():

    # Step 1 — Verify token
    try:
        user_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401

    uid = _resolve_user_id(user_id)
    if not uid:
        return jsonify({'error': 'User not found'}), 401

    # Step 2 — Get request data
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Step 3 — Validate cards data
    cards_data = data.get('cards', [])
    if not cards_data:
        return jsonify({'error': 'No cards data provided'}), 400

    template_count = len(cards_data)
    if template_count < 1 or template_count > 5:
        return jsonify({'error': 'Cards must be between 1 and 5'}), 400

    # STEP 4 — CREDIT CHECK AND DEDUCTION
    credit_cost = CREDIT_COST[template_count]
    current_credits = get_user_credits(uid)

    print(f"💳 User [{uid}] credits: {current_credits} | Cost: {credit_cost}")

    if current_credits < credit_cost:
        return jsonify({
            'status':           'error',
            'message':          f'Insufficient credits. You have {current_credits} but need {credit_cost}',
            'current_credits':  current_credits,
            'required_credits': credit_cost,
        }), 402

    # Create processing record
    req_id = f"gen_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    proc_record_id = ProcessingRecordModel.create(
        user_id=uid,
        processing_type="cards_image",
        document_count=template_count,
        credit_cost=credit_cost,
        request_id=req_id
    )

    # Deduct credits
    success, result = deduct_credits(
        user_id=uid,
        amount=credit_cost,
        reason=f"Fayda card generation ({template_count} cards)",
        processing_id=proc_record_id
    )
    if not success:
        ProcessingRecordModel.mark_failed(proc_record_id, str(result))
        return jsonify({'error': result}), 402

    remaining_credits = result
    print(f"✅ Credits deducted. Remaining: {remaining_credits}")

    # Step 5 — Merge edited texts into extracted texts
    for card in cards_data:
        extracted = card.get('extracted_texts', {})
        edited    = card.get('edited_texts', {})
        extracted.update(edited)
        card['extracted_texts'] = extracted

    # Step 6 — Generate PNG
    try:
        png_bytes = generate_final_png(cards_data, template_count)
        ProcessingRecordModel.mark_completed(proc_record_id)
    except Exception as e:
        print(f"❌ PNG generation failed: {e}")
        # Automatic refund on failure
        deduct_credits(
            user_id=uid,
            amount=-credit_cost,
            reason=f"Refund: generation failed: {str(e)[:100]}",
            processing_id=proc_record_id
        )
        ProcessingRecordModel.mark_failed(proc_record_id, f"PNG generation failed: {str(e)}")
        return jsonify({'error': f'PNG generation failed: {str(e)}'}), 500

    # Step 7 — Return PNG
    return send_file(
        io.BytesIO(png_bytes),
        mimetype='image/png',
        as_attachment=True,
        download_name='fayda_id_cards.png'
    )

# ============================================================
# ENDPOINT 3 — Add to Queue (WITH CREDIT DEDUCTION)
# ============================================================

@fayda_bp.route('/add-to-queue', methods=['POST'])
def add_to_queue():

    # Step 1 — Verify token
    try:
        user_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401

    # Step 2 — Parse body
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body is required'}), 400

    # Step 3 — Validate fields
    cards          = body.get('cards', [])
    template_count = body.get('template_count', 1)

    if not cards:
        return jsonify({'error': 'cards array is required'}), 400

    if template_count not in CREDIT_COST:
        return jsonify({'error': 'template_count must be between 1 and 5'}), 400

    # Step 4 — Validate each card
    for i, card in enumerate(cards):
        if 'extracted_texts' not in card:
            return jsonify({'error': f'Card {i+1} is missing extracted_texts'}), 400
        if 'profile_image' not in card:
            return jsonify({'error': f'Card {i+1} is missing profile_image'}), 400
        if 'qr_image' not in card:
            return jsonify({'error': f'Card {i+1} is missing qr_image'}), 400

    # Step 5 — Calculate credit cost
    credit_cost     = CREDIT_COST[template_count]
    current_credits = get_user_credits(user_id)

    print(f"💳 User [{user_id}] credits: {current_credits} | Cost: {credit_cost}")

    # Step 6 — Check credits
    if current_credits < credit_cost:
        return jsonify({
            'status':           'error',
            'message':          f'Insufficient credits. You have {current_credits} but need {credit_cost}',
            'current_credits':  current_credits,
            'required_credits': credit_cost,
        }), 402

    # Step 7 — Deduct credits
    success, result = deduct_credits(user_id, credit_cost)
    if not success:
        return jsonify({'error': result}), 402

    remaining_credits = result
    print(f"✅ Credits deducted. Remaining: {remaining_credits}")

    # Step 8 — Merge edited texts
    for card in cards:
        extracted = card.get('extracted_texts', {})
        edited    = card.get('edited_texts', {})
        extracted.update(edited)
        card['extracted_texts'] = extracted

    # Step 9 — Build job data
    now      = datetime.now(timezone.utc).isoformat()
    job_data = {
        'user_id':        user_id,
        'template_count': template_count,
        'credit_cost':    credit_cost,
        'cards':          cards,
        'status':         'pending',
        'created_at':     now,
        'updated_at':     now,
        'result_url':     None,
        'error':          None,
    }

    # Step 10 — Save to Firestore
    doc_ref            = db.collection('print_queue').document()
    job_data['job_id'] = doc_ref.id
    doc_ref.set(job_data)

    print(f"✅ Job [{doc_ref.id}] added to queue for user [{user_id}]")

    return jsonify({
        'status':            'success',
        'message':           'Job added to queue successfully',
        'job_id':            doc_ref.id,
        'template_count':    template_count,
        'credit_cost':       credit_cost,
        'remaining_credits': remaining_credits,
    }), 200

# ============================================================
# ENDPOINT 4 — Queue Status (check single job)
# ============================================================

@fayda_bp.route('/queue-status/<job_id>', methods=['GET'])
def queue_status(job_id):

    # Step 1 — Verify token
    try:
        user_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401

    # Step 2 — Get job from Firestore
    doc = db.collection('print_queue').document(job_id).get()
    if not doc.exists:
        return jsonify({'error': f'Job {job_id} not found'}), 404

    job = doc.to_dict()

    # Step 3 — Security: only owner can check their job
    if job.get('user_id') != user_id:
        return jsonify({'error': 'Unauthorized'}), 403

    return jsonify({
        'status':         'success',
        'job_id':         job_id,
        'job_status':     job.get('status'),
        'template_count': job.get('template_count'),
        'credit_cost':    job.get('credit_cost'),
        'created_at':     job.get('created_at'),
        'result_url':     job.get('result_url'),
        'error':          job.get('error'),
    }), 200

# ============================================================
# ENDPOINT 5 — My Jobs (get all jobs for user)
# ============================================================

@fayda_bp.route('/my-jobs', methods=['GET'])
def my_jobs():

    # Step 1 — Verify token
    try:
        user_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401

    # Step 2 — Get all jobs for this user (sorted in Python)
    try:
        jobs_ref = db.collection('print_queue')\
                     .where('user_id', '==', user_id)\
                     .stream()

        jobs_list = sorted(
            [{'job_id': j.id, **j.to_dict()} for j in jobs_ref],
            key=lambda x: x.get('created_at', ''),
            reverse=True
        )[:20]  # limit to 20

    except Exception as e:
        return jsonify({'error': f'Failed to fetch jobs: {str(e)}'}), 500

    result = []
    for j in jobs_list:
        result.append({
            'job_id':         j.get('job_id'),
            'job_status':     j.get('status'),
            'template_count': j.get('template_count'),
            'credit_cost':    j.get('credit_cost'),
            'created_at':     j.get('created_at'),
            'result_url':     j.get('result_url'),
        })

    return jsonify({
        'status': 'success',
        'jobs':   result,
        'total':  len(result),
    }), 200

# ============================================================
# ENDPOINT 6 — Process Queue
# ============================================================

@fayda_bp.route('/process-queue', methods=['POST'])
def process_queue():

    # Step 1 — Verify token
    try:
        user_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401

    # Step 2 — Get all pending jobs for this user (sorted in Python)
    try:
        jobs_ref = db.collection('print_queue')\
                     .where('user_id', '==', user_id)\
                     .where('status', '==', 'pending')\
                     .stream()

        jobs = sorted(
            [{'job_id': j.id, **j.to_dict()} for j in jobs_ref],
            key=lambda x: x.get('created_at', '')
        )
    except Exception as e:
        return jsonify({'error': f'Failed to fetch queue: {str(e)}'}), 500

    # Step 3 — Check if queue is empty
    if not jobs:
        return jsonify({
            'status':  'error',
            'message': 'No pending jobs in queue'
        }), 400

    # Step 4 — Check max 5 cards
    if len(jobs) > 5:
        return jsonify({
            'status':  'error',
            'message': f'Queue has {len(jobs)} jobs but max is 5'
        }), 400

    print(f"\n🖨️ Processing queue for user [{user_id}]")
    print(f"📋 Found {len(jobs)} pending job(s)")

    # Step 5 — Collect all cards from all jobs
    all_cards      = []
    all_job_ids    = []
    template_count = len(jobs)

    for job in jobs:
        job_id = job.get('job_id')
        cards  = job.get('cards', [])
        all_job_ids.append(job_id)

        for card in cards:
            extracted = card.get('extracted_texts', {})
            edited    = card.get('edited_texts', {})
            extracted.update(edited)
            card['extracted_texts'] = extracted
            all_cards.append(card)

        print(f"  ✅ Job [{job_id}] — {len(cards)} card(s) collected")

    print(f"📦 Total cards to process: {len(all_cards)}")
    print(f"🖼️  Using template: {template_count}-card-template.pdf")

    # Step 6 — Mark all jobs as "processing"
    try:
        now = datetime.now(timezone.utc).isoformat()
        for job_id in all_job_ids:
            db.collection('print_queue').document(job_id).update({
                'status':     'processing',
                'updated_at': now,
            })
        print(f"✅ Jobs marked as processing")
    except Exception as e:
        print(f"⚠️ Failed to mark jobs as processing: {e}")

    # Step 7 — Generate PNG
    try:
        png_bytes = generate_final_png(all_cards, template_count)
        print(f"✅ PNG generated successfully")
    except Exception as e:
        now = datetime.now(timezone.utc).isoformat()
        for job_id in all_job_ids:
            db.collection('print_queue').document(job_id).update({
                'status':     'failed',
                'error':      str(e),
                'updated_at': now,
            })
        print(f"❌ PNG generation failed: {e}")
        return jsonify({'error': f'PNG generation failed: {str(e)}'}), 500

    # Step 8 — Mark all jobs as "completed"
    try:
        now = datetime.now(timezone.utc).isoformat()
        for job_id in all_job_ids:
            db.collection('print_queue').document(job_id).update({
                'status':     'completed',
                'updated_at': now,
                'error':      None,
            })
        print(f"✅ Jobs marked as completed")
    except Exception as e:
        print(f"⚠️ Failed to mark jobs as completed: {e}")

    # Step 9 — Return PNG
    return send_file(
        io.BytesIO(png_bytes),
        mimetype='image/png',
        as_attachment=True,
        download_name='fayda_id_cards.png'
    )

# ============================================================
# ENDPOINT 7 — Process PDF Template (WITH CREDIT DEDUCTION)
# ============================================================

@fayda_bp.route('/process-pdf-template', methods=['POST'])
def process_pdf_template():

    # Step 1 — Verify token
    try:
        user_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401

    uid = _resolve_user_id(user_id)
    if not uid:
        return jsonify({'error': 'User not found'}), 401

    # Step 2 — Validate uploaded PDFs
    pdf_files = []
    for i in range(1, 6):  # pdf_1 to pdf_5
        key = f'pdf_{i}'
        if key in request.files:
            pdf_files.append(request.files[key])

    if not pdf_files:
        return jsonify({'error': 'At least one PDF file is required (pdf_1 to pdf_5)'}), 400

    if len(pdf_files) > 5:
        return jsonify({'error': 'Maximum 5 PDF files allowed'}), 400

    # Step 3 — Validate file types
    for i, f in enumerate(pdf_files):
        if f.mimetype not in ('application/pdf', 'application/octet-stream'):
            return jsonify({'error': f'File {i+1} must be a PDF'}), 400

    print(f"\n📄 Processing {len(pdf_files)} PDF file(s) for user [{uid}]")

    # STEP 4 — CREDIT CHECK AND DEDUCTION FOR PDF MODE
    template_count = len(pdf_files)
    credit_cost = CREDIT_COST[template_count]
    current_credits = get_user_credits(uid)

    print(f"💳 User [{uid}] credits: {current_credits} | Cost: {credit_cost}")

    if current_credits < credit_cost:
        return jsonify({
            'status':           'error',
            'message':          f'Insufficient credits. You have {current_credits} but need {credit_cost}',
            'current_credits':  current_credits,
            'required_credits': credit_cost,
        }), 402

    # Create processing record
    req_id = f"pdf_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    proc_record_id = ProcessingRecordModel.create(
        user_id=uid,
        processing_type="pdf_template",
        document_count=template_count,
        credit_cost=credit_cost,
        request_id=req_id
    )

    # Deduct credits
    success, result = deduct_credits(
        user_id=uid,
        amount=credit_cost,
        reason=f"Fayda PDF Processing ({template_count} cards)",
        processing_id=proc_record_id
    )
    if not success:
        ProcessingRecordModel.mark_failed(proc_record_id, str(result))
        return jsonify({'error': result}), 402

    remaining_credits = result
    print(f"✅ Credits deducted. Remaining: {remaining_credits}")

    # Step 5 — Extract data from each PDF
    from services.gemini import extract_from_pdf

    all_cards = []

    for i, pdf_file in enumerate(pdf_files):
        print(f"\n📄 Processing PDF {i+1}/{template_count}: {pdf_file.filename}")
        try:
            extracted_texts, profile_b64, qr_b64 = extract_from_pdf(pdf_file)

            card = {
                'extracted_texts': extracted_texts,
                'profile_image':   profile_b64,
                'qr_image':        qr_b64,
                'use_black_and_white': False,
                'use_white_bg':        False,
            }
            all_cards.append(card)
            print(f"  ✅ PDF {i+1} extracted successfully")

        except Exception as e:
            print(f"  ❌ PDF {i+1} extraction failed: {e}")
            print(traceback.format_exc())
            # Refund credits if extraction fails
            deduct_credits(
                user_id=uid,
                amount=-credit_cost,
                reason=f"Refund: extraction error on PDF {i+1}",
                processing_id=proc_record_id
            )
            ProcessingRecordModel.mark_failed(proc_record_id, f"Extraction failed on PDF {i+1}: {str(e)}")
            return jsonify({
                'error': f'Failed to extract data from PDF {i+1}: {str(e)}'
            }), 500

    print(f"\n📦 Total cards extracted: {len(all_cards)}")
    print(f"🖼️  Using template: {template_count}-card-template.pdf")

    # Step 6 — Generate PNG
    try:
        png_bytes = generate_final_png(all_cards, template_count)
        ProcessingRecordModel.mark_completed(proc_record_id)
        print(f"✅ PNG generated successfully")
    except Exception as e:
        print(f"❌ PNG generation failed: {e}")
        print(traceback.format_exc())
        # Refund credits if generation fails
        deduct_credits(
            user_id=uid,
            amount=-credit_cost,
            reason="Refund: PNG generation error",
            processing_id=proc_record_id
        )
        ProcessingRecordModel.mark_failed(proc_record_id, f"PNG generation failed: {str(e)}")
        return jsonify({'error': f'PNG generation failed: {str(e)}'}), 500

    # Step 7 — Return PNG
    return send_file(
        io.BytesIO(png_bytes),
        mimetype='image/png',
        as_attachment=True,
        download_name='fayda_id_cards.png'
    )

# ============================================================
# ENDPOINT 8 — Process Photo (BG Remove + Color)
# ============================================================

@fayda_bp.route('/process-photo', methods=['POST'])
def process_photo():

    # Step 1 — Verify token
    try:
        user_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401

    # Step 2 — Parse body
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body is required'}), 400

    profile_image_b64 = body.get('profile_image', '')
    remove_bg         = body.get('remove_bg', False)
    grayscale         = body.get('grayscale', False)

    if not profile_image_b64:
        return jsonify({'error': 'profile_image is required'}), 400

    print(f"\n🖼️  Processing photo | remove_bg: {remove_bg} | grayscale: {grayscale}")

    try:
        from PIL import Image
        import base64
        import io
        import tempfile
        import os

        # ── Decode base64 to PIL ──
        img_data  = base64.b64decode(profile_image_b64)
        pil_image = Image.open(io.BytesIO(img_data)).convert('RGBA')

        print(f"📸 Image size: {pil_image.width}x{pil_image.height}")

        # ── Remove background using Replicate ──
        if remove_bg:
            print("🔄 Removing background via Replicate...")
            try:
                import replicate
                import urllib.request

                # Save image to temp file
                with tempfile.NamedTemporaryFile(
                    suffix='.png',
                    delete=False
                ) as tmp:
                    pil_image.convert('RGB').save(tmp.name, format='PNG')
                    tmp_path = tmp.name

                # Send to Replicate
                with open(tmp_path, 'rb') as img_file:
                    output = replicate.run(
                        "851-labs/background-remover:a029dff38972b5fda4ec5d75d7d1cd25aeff621d2cf4946a41055d7db66b80bc",
                        input={"image": img_file}
                    )

                # Clean up temp file
                os.unlink(tmp_path)

                # Download result from Replicate URL
                result_bytes = output.read()
                pil_image    = Image.open(
                    io.BytesIO(result_bytes)
                ).convert('RGBA')

                print(f"✅ Background removed via Replicate")

            except Exception as e:
                print(f"❌ Replicate BG removal error: {e}")
                return jsonify({
                    'error': f'Background removal failed: {str(e)}'
                }), 500

        # ── Apply grayscale ──
        if grayscale:
            print("🔄 Converting to grayscale...")
            if pil_image.mode == 'RGBA':
                r, g, b, a = pil_image.split()
                gray        = Image.merge('RGB', (r, g, b)).convert('L')
                gray_rgba   = Image.merge('RGBA', (gray, gray, gray, a))
                pil_image   = gray_rgba
            else:
                pil_image = pil_image.convert('L').convert('RGBA')
            print(f"✅ Grayscale applied")

        # ── Convert back to base64 ──
        output_buffer = io.BytesIO()
        pil_image.save(output_buffer, format='PNG')
        output_b64 = base64.b64encode(
            output_buffer.getvalue()
        ).decode('utf-8')

        print(f"✅ Photo processed successfully")

        return jsonify({
            'status':        'success',
            'profile_image': output_b64,
            'remove_bg':     remove_bg,
            'grayscale':     grayscale,
        }), 200

    except Exception as e:
        print(f"❌ process_photo error: {e}")
        return jsonify({'error': str(e)}), 500
# ============================================================
# PAYMENT & ADMIN ENDPOINTS
# ============================================================

@fayda_bp.route('/submit-payment-request', methods=['POST'])
def submit_payment_request():
    """User submits payment request with receipt number"""
    try:
        user_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401
    
    data = request.json
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    receipt_number = data.get('receipt_number')
    payment_method = data.get('payment_method')
    credits = data.get('credits')
    amount = data.get('amount')
    package_id = data.get('package_id')
    user_email = data.get('user_email')
    user_name = data.get('user_name')
    
    if not receipt_number or not payment_method or not credits:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Create payment request
    payment_data = {
        'user_id': user_id,
        'user_email': user_email,
        'user_name': user_name,
        'package_id': package_id,
        'credits': credits,
        'amount': amount,
        'payment_method': payment_method,
        'receipt_number': receipt_number,
        'status': 'pending',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    
    # Save to Firestore
    doc_ref = db.collection('payment_requests').document()
    payment_data['id'] = doc_ref.id
    doc_ref.set(payment_data)
    
    print(f"✅ Payment request submitted: {doc_ref.id} for user {user_email}")
    
    return jsonify({
        'status': 'success',
        'message': 'Payment request submitted successfully. Admin will verify and add credits within 24 hours.',
        'request_id': doc_ref.id
    }), 200


@fayda_bp.route('/admin/payment-requests', methods=['GET'])
def admin_list_payment_requests():
    """Admin gets all payment requests"""
    try:
        admin_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401
    
    if not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
    
    payments = db.collection('payment_requests').order_by('created_at', direction='DESC').stream()
    result = []
    for p in payments:
        data = p.to_dict()
        data['id'] = p.id
        result.append(data)
    
    return jsonify({'payments': result}), 200


@fayda_bp.route('/admin/users', methods=['GET'])
def admin_list_users():
    """Admin gets all users"""
    try:
        admin_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401
    
    if not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
    
    users = db.collection('users').stream()
    result = []
    for u in users:
        data = u.to_dict()
        data['uid'] = u.id
        result.append(data)
    
    return jsonify({'users': result}), 200


@fayda_bp.route('/admin/approve-payment', methods=['POST'])
def admin_approve_payment_request():
    """Admin approves payment and adds credits to user"""
    try:
        admin_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401
    
    if not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
    
    data = request.json
    payment_id = data.get('payment_id')
    user_id = data.get('user_id')
    credits = data.get('credits')
    
    if not payment_id or not user_id or not credits:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Update payment status
    payment_ref = db.collection('payment_requests').document(payment_id)
    payment_ref.update({
        'status': 'approved',
        'approved_by': admin_id,
        'approved_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat()
    })
    
    # Add credits to user
    user_ref = db.collection('users').document(user_id)
    user = user_ref.get()
    current_credits = user.to_dict().get('credits', 0)
    user_ref.update({
        'credits': current_credits + credits,
        'updated_at': datetime.now(timezone.utc).isoformat()
    })
    
    print(f"✅ Payment {payment_id} approved by admin {admin_id}. Added {credits} credits to user {user_id}")
    
    return jsonify({'status': 'success', 'message': 'Payment approved and credits added'}), 200


@fayda_bp.route('/admin/reject-payment', methods=['POST'])
def admin_reject_payment_request():
    """Admin rejects payment request"""
    try:
        admin_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401
    
    if not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
    
    data = request.json
    payment_id = data.get('payment_id')
    
    if not payment_id:
        return jsonify({'error': 'Missing payment_id'}), 400
    
    # Update payment status
    payment_ref = db.collection('payment_requests').document(payment_id)
    payment_ref.update({
        'status': 'rejected',
        'rejected_by': admin_id,
        'rejected_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat()
    })
    
    print(f"❌ Payment {payment_id} rejected by admin {admin_id}")
    
    return jsonify({'status': 'success', 'message': 'Payment rejected'}), 200


@fayda_bp.route('/admin/add-credits', methods=['POST'])
def admin_add_credits_to_user():
    """Admin manually adds credits to a user. Only admin can call this."""
    try:
        admin_id = verify_token(request)
    except Exception as e:
        err_msg = str(e)
        if err_msg.startswith("EMAIL_NOT_VERIFIED:"):
            return jsonify({'error': err_msg, 'code': 'EMAIL_NOT_VERIFIED'}), 403
        return jsonify({'error': err_msg}), 401

    if not is_admin(admin_id):
        return jsonify({'error': 'Unauthorized. Admin access required.'}), 403

    data = request.json or {}
    user_id = data.get('user_id')
    credits = data.get('credits')
    reason = data.get('reason', 'Admin credit grant')

    if not user_id or not isinstance(credits, int) or credits < 1:
        return jsonify({'error': 'Invalid user_id or credits amount (must be integer >= 1)'}), 400

    # Resolve target user in SQLite
    target_user = UserModel.get_by_id(int(user_id)) if str(user_id).isdigit() else UserModel.get_by_email(str(user_id))
    if not target_user:
        return jsonify({'error': 'User not found'}), 404

    # Record ADMIN_GRANT transaction in credit ledger
    success, message, new_balance = CreditLedgerModel.record_transaction(
        user_id=target_user['id'],
        amount=credits,
        transaction_type='ADMIN_GRANT',
        reason=reason,
        admin_id=admin_id
    )

    if not success:
        return jsonify({'error': message}), 500

    print(f"✅ Admin [{admin_id}] granted {credits} credits to user [{target_user['id']}] {target_user['email']} | new balance: {new_balance}")

    return jsonify({
        'status': 'success',
        'message': f'Added {credits} credits to {target_user["email"]}',
        'user_id': target_user['id'],
        'email': target_user['email'],
        'credits_added': credits,
        'new_balance': new_balance
    }), 200