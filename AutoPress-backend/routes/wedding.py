from flask import Blueprint, request, jsonify, send_file
from fb.admin import verify_token, db
import fitz
import io
import os
import math

wedding_bp = Blueprint('wedding', __name__, url_prefix='/api/wedding')

# ============================================================
# PATHS
# ============================================================
WEDDING_TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'templates', 'wedding'
)
FONTS_DIR         = os.path.join(os.path.dirname(__file__), '..', 'fonts')
AMHARIC_FONT_PATH = os.path.join(FONTS_DIR, 'VisualGeezUnicode.ttf')
ENGLISH_FONT_PATH = os.path.join(FONTS_DIR, 'Roboto-SemiBold.ttf')

# ============================================================
# CREDIT COST PER QUANTITY
# ============================================================
def calculate_credit_cost(quantity):
    if quantity <= 50:
        return 1
    elif quantity <= 100:
        return 2
    elif quantity <= 200:
        return 3
    elif quantity <= 500:
        return 5
    else:
        return 8

# ============================================================
# SYSTEM TEMPLATES
# ============================================================
SYSTEM_TEMPLATES = {
    "wedding-1": {
        "id":          "wedding-1",
        "name":        "Classic Elegance",
        "description": "Traditional Ethiopian wedding card",
        "language":    "both",
        "preview":     "/static/previews/wedding-1.png",
        "file":        "wedding-1.png",
    },
    "wedding-2": {
        "id":          "wedding-2",
        "name":        "Modern Gold",
        "description": "Modern style with gold accents",
        "language":    "both",
        "preview":     "/static/previews/wedding-2.png",
        "file":        "wedding-2.png",
    },
    "wedding-3": {
        "id":          "wedding-3",
        "name":        "Floral Rose",
        "description": "Elegant floral design",
        "language":    "both",
        "preview":     "/static/previews/wedding-3.png",
        "file":        "wedding-3.png",
    },
    "wedding-4": {
        "id":          "wedding-4",
        "name":        "Royal Blue",
        "description": "Royal blue and white design",
        "language":    "both",
        "preview":     "/static/previews/wedding-4.png",
        "file":        "wedding-4.png",
    },
    "wedding-5": {
        "id":          "wedding-5",
        "name":        "Amharic Traditional",
        "description": "Full Amharic traditional design",
        "language":    "amharic",
        "preview":     "/static/previews/wedding-5.png",
        "file":        "wedding-5.png",
    },
}

# ============================================================
# TEMPLATE FIELD COORDINATES (PNG pixel coordinates)
# ============================================================
TEMPLATE_FIELDS = {
    "wedding-1": [

        # ── Name 1 (groom if ILMA, bride if INTALA) ──
        {
            "key":      "name1",
            "x":        450,
            "y":        650,
            "fontSize": 50,
            "font":     "english",
            "rotation": 0
        },

        # ── Name 2 (bride if ILMA, groom if INTALA) ──
        {
            "key":      "name2",
            "x":        450,
            "y":        850,
            "fontSize": 50,
            "font":     "english",
            "rotation": 0
        },

        # ── Date inside sentence (rawwatamu___) ──
        {
            "key":      "wedding_date_sentence",
            "x":        680,
            "y":        930,
            "fontSize": 30,
            "font":     "english",
            "rotation": 0
        },

        # ── Time (sa'ati____) ──
        {
            "key":      "wedding_time",
            "x":        380,
            "y":        970,
            "fontSize": 35,
            "font":     "english",
            "rotation": 0
        },

        # ── Day (e.g Jimaata) ──
        {
            "key":      "wedding_day",
            "x":        350,
            "y":        1200,
            "fontSize": 40,
            "font":     "english",
            "rotation": 0
        },

        # ── Month ──
        {
            "key":      "wedding_month",
            "x":        600,
            "y":        1200,
            "fontSize": 40,
            "font":     "english",
            "rotation": 0
        },

        # ── Year ──
        {
            "key":      "wedding_year",
            "x":        750,
            "y":        1200,
            "fontSize": 40,
            "font":     "english",
            "rotation": 0
        },

        # ── Father name ──
        {
            "key":      "father_name",
            "x":        450,
            "y":        1350,
            "fontSize": 50,
            "font":     "english",
            "rotation": 0
        },

        # ── Mother name ──
        {
            "key":      "mother_name",
            "x":        450,
            "y":        1420,
            "fontSize": 50,
            "font":     "english",
            "rotation": 0
        },

        # ── Address/Location (TEESSON:) ──
        {
            "key":      "venue_address",
            "x":        450,
            "y":        1550,
            "fontSize": 50,
            "font":     "english",
            "rotation": 0
        },
    ],
    "wedding-2": [
        # ── Name 1 (groom if ILMA, bride if INTALA) ──
        {
            "key":      "name1",
            "x":        250,
            "y":        600,
            "fontSize": 50,
            "font":     "english",
            "rotation": 0
        },

        # ── Name 2 (bride if ILMA, groom if INTALA) ──
        {
            "key":      "name2",
            "x":        700,
            "y":        600,
            "fontSize": 50,
            "font":     "english",
            "rotation": 0
        },

        # ── Date inside sentence (rawwatamu___) ──
        {
            "key":      "wedding_date_sentence",
            "x":        680,
            "y":        930,
            "fontSize": 30,
            "font":     "english",
            "rotation": 0
        },

        # ── Time (sa'ati____) ──
        {
            "key":      "wedding_time",
            "x":        380,
            "y":        970,
            "fontSize": 35,
            "font":     "english",
            "rotation": 0
        },

        # ── Day (e.g Jimaata) ──
        {
            "key":      "wedding_day",
            "x":        350,
            "y":        1150,
            "fontSize": 40,
            "font":     "english",
            "rotation": 0
        },

        # ── Month ──
        {
            "key":      "wedding_month",
            "x":        600,
            "y":        1150,
            "fontSize": 40,
            "font":     "english",
            "rotation": 0
        },

        # ── Year ──
        {
            "key":      "wedding_year",
            "x":        750,
            "y":        1150,
            "fontSize": 40,
            "font":     "english",
            "rotation": 0
        },

        # ── Father name ──
        {
            "key":      "father_name",
            "x":        450,
            "y":        1300,
            "fontSize": 50,
            "font":     "english",
            "rotation": 0
        },

        # ── Mother name ──
        {
            "key":      "mother_name",
            "x":        450,
            "y":        1370,
            "fontSize": 50,
            "font":     "english",
            "rotation": 0
        },

        # ── Address/Location (TEESSON:) ──
        {
            "key":      "venue_address",
            "x":        540,
            "y":        1440,
            "fontSize": 50,
            "font":     "english",
            "rotation": 0
        },
    ],
    "wedding-3": [],
    "wedding-4": [],
    "wedding-5": [],
}

# ============================================================
# REQUIRED FIELDS
# ============================================================
REQUIRED_FIELDS = [
    'card_mode',             # "ilma" or "intala"
    'name1',                 # person 1
    'name2',                 # person 2
    'wedding_date_sentence', # date in sentence
    'wedding_time',          # time
    'wedding_day',           # day name
    'wedding_month',         # month name
    'wedding_year',          # year
    'father_name',           # father
    'mother_name',           # mother
    'venue_address',         # location
]

# ============================================================
# HELPER — Draw text on card image
# ============================================================
def draw_card(template_img, fields, form_data, language):
    card_img = template_img.copy()
    draw     = ImageDraw.Draw(card_img)

    for field in fields:
        key       = field.get('key', '')
        value     = form_data.get(key, '')

        # Skip empty
        if not value:
            continue

        # Skip language specific
        if language == 'amharic' and field.get('font') == 'english':
            continue
        if language == 'english' and field.get('font') == 'amharic':
            continue

        fx        = field.get('x', 0)
        fy        = field.get('y', 0)
        font_size = field.get('fontSize', 20)
        font_type = field.get('font', 'english')

        # Load font
        try:
            if font_type == 'amharic':
                font = ImageFont.truetype(AMHARIC_FONT_PATH, size=font_size)
            else:
                font = ImageFont.truetype(ENGLISH_FONT_PATH, size=font_size)
        except Exception:
            font = ImageFont.load_default()

        draw.text(
            (fx, fy),
            str(value),
            fill=(0, 0, 0, 255),
            font=font
        )
        print(f"  ✅ [{key}]: '{value}'")

    return card_img

# ============================================================
# ENDPOINT 1 — GET /wedding/templates
# ============================================================

@wedding_bp.route('/wedding/templates', methods=['GET'])
def get_templates():

    # Step 1 — Verify token
    try:
        user_id = verify_token(request)
    except Exception as e:
        return jsonify({'error': str(e)}), 401

    print(f"\n💍 Get templates for user [{user_id}]")

    # Step 2 — Build templates list
    templates_list = []
    for tid, template in SYSTEM_TEMPLATES.items():
        template_path = os.path.join(
            WEDDING_TEMPLATES_DIR,
            template['file']
        )
        file_exists = os.path.exists(template_path)

        templates_list.append({
            'id':          template['id'],
            'name':        template['name'],
            'description': template['description'],
            'language':    template['language'],
            'preview':     template['preview'],
            'available':   file_exists,
        })

    print(f"✅ Returning {len(templates_list)} templates")

    return jsonify({
        'status':    'success',
        'templates': templates_list,
        'total':     len(templates_list),
    }), 200

# ============================================================
# ENDPOINT 2 — POST /wedding/generate
# ============================================================

@wedding_bp.route('/wedding/generate', methods=['POST'])
def generate_wedding():

    # Step 1 — Verify token
    try:
        user_id = verify_token(request)
    except Exception as e:
        return jsonify({'error': str(e)}), 401

    # Step 2 — Parse body
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body is required'}), 400

    template_id = body.get('template_id', '')
    quantity    = body.get('quantity', 1)
    language    = body.get('language', 'both')
    form_data   = body.get('form_data', {})

    # Step 3 — Validate template
    if not template_id or template_id not in SYSTEM_TEMPLATES:
        return jsonify({
            'error': f'Template [{template_id}] not found. Available: {list(SYSTEM_TEMPLATES.keys())}'
        }), 404

    # Step 4 — Validate quantity
    try:
        quantity = int(quantity)
    except Exception:
        return jsonify({'error': 'quantity must be a number'}), 400

    if quantity < 1 or quantity > 1000:
        return jsonify({'error': 'quantity must be between 1 and 1000'}), 400

    # Step 5 — Validate language
    if language not in ('amharic', 'english', 'both'):
        return jsonify({
            'error': 'language must be amharic, english or both'
        }), 400

    # Step 6 — Validate form data
    if not form_data:
        return jsonify({'error': 'form_data is required'}), 400

    missing = [f for f in REQUIRED_FIELDS if not form_data.get(f)]
    if missing:
        return jsonify({
            'error':   'Missing required fields',
            'missing': missing
        }), 400

    # Step 7 — Validate card_mode
    card_mode = form_data.get('card_mode', '')
    if card_mode not in ('ilma', 'intala'):
        return jsonify({
            'error': 'card_mode must be ilma or intala'
        }), 400

    # Step 8 — Check PNG template exists
    template_info = SYSTEM_TEMPLATES[template_id]
    png_path      = os.path.join(WEDDING_TEMPLATES_DIR, template_info['file'])

    if not os.path.exists(png_path):
        return jsonify({
            'error': f'Template PNG not found: {template_info["file"]}'
        }), 500

    # Step 9 — Calculate and check credits
    credit_cost     = calculate_credit_cost(quantity)
    current_credits = get_user_credits(user_id)

    print(f"\n💍 Wedding PNG generation")
    print(f"   User      : {user_id}")
    print(f"   Template  : {template_id}")
    print(f"   Quantity  : {quantity}")
    print(f"   Language  : {language}")
    print(f"   Card mode : {card_mode}")
    print(f"   Credits   : {current_credits} available | {credit_cost} required")

    if current_credits < credit_cost:
        return jsonify({
            'status':           'error',
            'message':          f'Insufficient credits. You have {current_credits} but need {credit_cost}',
            'current_credits':  current_credits,
            'required_credits': credit_cost,
        }), 402

    # Step 10 — Deduct credits
    success, result = deduct_credits(user_id, credit_cost)
    if not success:
        return jsonify({'error': result}), 402

    remaining_credits = result
    print(f"✅ Credits deducted. Remaining: {remaining_credits}")

    # Step 11 — Generate PDF
    try:
        # Load template PNG
        template_img   = Image.open(png_path).convert('RGBA')
        card_w, card_h = template_img.size
        print(f"📐 Card PNG size: {card_w} x {card_h} px")

        # Get field coordinates
        fields = TEMPLATE_FIELDS.get(template_id, [])

        # A4 at 300 DPI in pixels
        A4_W   = 2480
        A4_H   = 3508
        MARGIN = 40

        # ── Target layout: 2 cols x 3 rows = 6 cards per A4 ──
        TARGET_COLS = 2
        TARGET_ROWS = 2

        # Calculate card size to fit target layout
        fit_w = (A4_W - MARGIN * (TARGET_COLS + 1)) // TARGET_COLS
        fit_h = (A4_H - MARGIN * (TARGET_ROWS + 1)) // TARGET_ROWS

        # Resize template to fit
        template_img = template_img.resize((fit_w, fit_h), Image.LANCZOS)
        card_w, card_h = template_img.size

        cards_per_row  = TARGET_COLS
        cards_per_col  = TARGET_ROWS
        cards_per_page = cards_per_row * cards_per_col
        total_pages    = math.ceil(quantity / cards_per_page)

        print(f"📐 Resized card: {card_w} x {card_h} px")
        print(f"📄 Layout : {cards_per_row} cols x {cards_per_col} rows = {cards_per_page} cards/page")
        print(f"📄 Pages  : {total_pages} for {quantity} cards")

        # Build output PDF
        output_doc = fitz.open()
        cards_done = 0

        for page_num in range(total_pages):

            # Blank white A4
            a4_img = Image.new('RGBA', (A4_W, A4_H), (255, 255, 255, 255))

            for row in range(cards_per_col):
                for col in range(cards_per_row):
                    if cards_done >= quantity:
                        break

                    # Draw text on card
                    card_img = draw_card(
                        template_img,
                        fields,
                        form_data,
                        language
                    )

                    # Paste onto A4
                    paste_x = MARGIN + col * (card_w + MARGIN)
                    paste_y = MARGIN + row * (card_h + MARGIN)
                    a4_img.paste(card_img, (paste_x, paste_y), card_img)

                    cards_done += 1

                if cards_done >= quantity:
                    break

            # Convert A4 image → PDF page
            a4_rgb    = a4_img.convert('RGB')
            img_bytes = io.BytesIO()
            a4_rgb.save(img_bytes, format='PDF', resolution=300)
            img_bytes.seek(0)

            page_doc = fitz.open('pdf', img_bytes.read())
            output_doc.insert_pdf(page_doc)
            page_doc.close()

            print(f"✅ Page {page_num+1}/{total_pages} done ({cards_done}/{quantity} cards)")

        # Save to buffer
        output_buffer = io.BytesIO()
        output_doc.save(output_buffer)
        output_doc.close()
        output_buffer.seek(0)

        print(f"\n✅ Done! {quantity} cards on {total_pages} A4 pages")

    except Exception as e:
        # Refund credits on failure
        db.collection('users').document(user_id).update({
            'credits': current_credits
        })
        print(f"❌ Generation failed: {e}")
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500

    # Step 12 — Save job to Firestore
    try:
        now = datetime.now(timezone.utc).isoformat()
        db.collection('wedding_jobs').document().set({
            'user_id':           user_id,
            'template_id':       template_id,
            'quantity':          quantity,
            'language':          language,
            'card_mode':         card_mode,
            'credit_cost':       credit_cost,
            'remaining_credits': remaining_credits,
            'cards_per_page':    cards_per_page,
            'total_pages':       total_pages,
            'status':            'completed',
            'created_at':        now,
        })
        print(f"✅ Job saved to Firestore")
    except Exception as e:
        print(f"⚠️ Failed to save job: {e}")

    # Step 13 — Return PDF
    return send_file(
        output_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'wedding_cards_{quantity}pcs.pdf'
    )

# ============================================================
# ENDPOINT 3 — GET /wedding/my-jobs
# ============================================================

@wedding_bp.route('/wedding/my-jobs', methods=['GET'])
def wedding_my_jobs():

    # Step 1 — Verify token
    try:
        user_id = verify_token(request)
    except Exception as e:
        return jsonify({'error': str(e)}), 401

    # Step 2 — Get jobs from Firestore
    try:
        jobs_ref  = db.collection('wedding_jobs')\
                      .where('user_id', '==', user_id)\
                      .stream()

        jobs_list = sorted(
            [{'job_id': j.id, **j.to_dict()} for j in jobs_ref],
            key=lambda x: x.get('created_at', ''),
            reverse=True
        )[:20]

    except Exception as e:
        return jsonify({'error': f'Failed to fetch jobs: {str(e)}'}), 500

    result = []
    for j in jobs_list:
        result.append({
            'job_id':      j.get('job_id'),
            'template_id': j.get('template_id'),
            'quantity':    j.get('quantity'),
            'language':    j.get('language'),
            'card_mode':   j.get('card_mode'),
            'credit_cost': j.get('credit_cost'),
            'total_pages': j.get('total_pages'),
            'status':      j.get('status'),
            'created_at':  j.get('created_at'),
        })

    return jsonify({
        'status': 'success',
        'jobs':   result,
        'total':  len(result),
    }), 200