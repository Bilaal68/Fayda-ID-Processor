from google import genai
from google.genai import types
import os
import time
import json
import base64
import io
import re
import itertools
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# API KEY ROTATION
# ============================================================
GEMINI_API_KEYS = [
    os.getenv('GEMINI_API_KEY_1'),
    os.getenv('GEMINI_API_KEY_2'),
    os.getenv('GEMINI_API_KEY_3'),
    os.getenv('GEMINI_API_KEY_4'),
    os.getenv('GEMINI_API_KEY_5'),
    os.getenv('GEMINI_API_KEY_6'),
    os.getenv('GEMINI_API_KEY_7'),
    os.getenv('GEMINI_API_KEY_8'),
    os.getenv('GEMINI_API_KEY_9'),
    os.getenv('GEMINI_API_KEY_10'),
    os.getenv('GEMINI_API_KEY_11'),
    os.getenv('GEMINI_API_KEY_12'),
    os.getenv('GEMINI_API_KEY_13'),
    os.getenv('GEMINI_API_KEY_14'),
    os.getenv('GEMINI_API_KEY_15'),
    os.getenv('GEMINI_API_KEY_16'),
    os.getenv('GEMINI_API_KEY_17'),
    os.getenv('GEMINI_API_KEY_18'),
    os.getenv('GEMINI_API_KEY_19'),
    os.getenv('GEMINI_API_KEY_20'),
]

# ── Filter out None/empty keys ──
GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k]

if not GEMINI_API_KEYS:
    raise Exception("No Gemini API keys found in .env!")

print(f"✅ Loaded {len(GEMINI_API_KEYS)} Gemini API keys")

# ── Rotating key cycle ──
_key_cycle = itertools.cycle(GEMINI_API_KEYS)

def get_next_key():
    """Get next API key in rotation"""
    return next(_key_cycle)

# ============================================================
# MODELS (KEPT AS YOU HAVE THEM - NOT CHANGED)
# ============================================================
MODELS_TO_TRY = [
    'gemini-3-flash-preview',
    'gemini-3.1-flash-lite-preview',
    'gemini-2.5-flash',
]

# ============================================================
# PROMPTS
# ============================================================
JSON_SYSTEM_INSTRUCTION = "You are a precise data extractor. Always return output as valid JSON only. Never add markdown, explanations, or any text outside the JSON object."

TEXT_EXTRACTION_PROMPT = """
You are an Ethiopian Fayda ID card data extractor.

You are given 3 images:
- Image 1 (Front): Contains English Name, Amharic Name, Date of Birth, Sex, FIN number
- Image 2 (Back): Contains Region, Zone, Woreda, Phone number in both Amharic and English
- Image 3 (Profile+QR): Contains the profile photo and FAN barcode number

Extract ALL text fields carefully from each image.

Return ONLY this exact JSON object:
{
    "extracted_texts": {
        "amharic_name": "",
        "english_name": "",
        "amharic_birth": "",
        "english_birth": "",
        "amharic_sex": "",
        "english_sex": "",
        "amharic_region": "",
        "english_region": "",
        "amharic_zone": "",
        "english_zone": "",
        "amharic_woreda": "",
        "english_woreda": "",
        "phone": "",
        "fin": "",
        "fan": "",
        "issueDateGregorian": "",
        "issueDateEthiopian": "",
        "expiryDateGregorian": "",
        "expiryDateEthiopian": ""
    }
}

Rules:
- Return ONLY the JSON object, no extra text at all
- If a field is not visible leave it as empty string ""
- FAN is the number used for barcode generation (from Image 3)
- FIN is the national ID number (from Image 1)
- amharic_birth: Ethiopian calendar date using ARABIC numbers only (e.g. "27/9/1998")
- english_birth: Gregorian calendar date using ARABIC numbers only (e.g. "04/06/2006")
- issueDateEthiopian: the issue date in ETHIOPIAN calendar (smaller year number e.g. 2018)
- issueDateGregorian: the issue date in GREGORIAN calendar (larger year number e.g. 2026)
- expiryDateEthiopian: the expiry date in ETHIOPIAN calendar (smaller year number e.g. 2034)
- expiryDateGregorian: the expiry date in GREGORIAN calendar (larger year number e.g. 2042)
- Ethiopian calendar year is ALWAYS smaller than Gregorian year by about 7-8 years
- All numbers in ALL fields must be Arabic numerals (0-9), never Ethiopic numerals
"""

PROFILE_COORD_PROMPT = """
This image contains a white box that has TWO sections inside it:
- TOP section: a profile photo of a person inside a bright white rectangle
- BOTTOM section: a QR code

Focus ONLY on the TOP section — the profile photo.

The profile photo has:
- A person's photo
- An extremely bright white rectangle tightly around the person photo only

Crop ONLY the profile photo and its immediate white rectangle border.
Stop BEFORE the QR code starts.
Do NOT include the QR code or anything below the profile photo.

Return coordinates in normalized format (0-1000) where:
- [0, 0] is the TOP-LEFT corner
- [1000, 1000] is the BOTTOM-RIGHT corner

Return ONLY this JSON:
{
    "x1": left edge (0-1000),
    "y1": top edge (0-1000),
    "x2": right edge (0-1000),
    "y2": bottom edge (0-1000)
}

Make sure x1 < x2 and y1 < y2.
"""

QR_COORD_PROMPT = """
This image contains a QR code in the BOTTOM area.

Find the QR code region including:
- Full QR code matrix
- White border around the QR code
- If QR code has plastic glare, expand bounding box by 5% to ensure
  no alignment patterns are cut off
Exclude:
- Any text above or below the QR code
- Any other UI elements

Return coordinates in normalized format (0-1000) where:
- [0, 0] is the TOP-LEFT corner
- [1000, 1000] is the BOTTOM-RIGHT corner

Return ONLY this JSON:
{
    "x1": left edge (0-1000),
    "y1": top edge (0-1000),
    "x2": right edge (0-1000),
    "y2": bottom edge (0-1000)
}

Make sure x1 < x2 and y1 < y2.
"""

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def image_to_base64(pil_image, format='PNG'):
    """Convert PIL image to base64 string"""
    buffer = io.BytesIO()
    pil_image.save(buffer, format=format)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')

def parse_gemini_json(response_text):
    """Clean and parse JSON from Gemini response"""
    text = response_text.strip()
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    return json.loads(text.strip())

def crop_image(img, coords, img_width, img_height):
    """Crop image using normalized coordinates (0-1000) from Gemini"""
    x1 = int((coords['x1'] / 1000) * img_width)
    y1 = int((coords['y1'] / 1000) * img_height)
    x2 = int((coords['x2'] / 1000) * img_width)
    y2 = int((coords['y2'] / 1000) * img_height)

    if x1 > x2: x1, x2 = x2, x1
    if y1 > y2: y1, y2 = y2, y1

    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(img_width, x2)
    y2 = min(img_height, y2)

    if x2 <= x1: x2 = x1 + 10
    if y2 <= y1: y2 = y1 + 10

    print(f"✂️  Cropping: ({x1},{y1}) → ({x2},{y2})")
    return img.crop((x1, y1, x2, y2))

def call_gemini_with_rotation(parts, system_instruction=None):
    """
    Call Gemini with automatic API key rotation and network retry.
    Handles rate limits (429), server errors (503), and temporary network/DNS blips.
    """
    last_error = None
    num_keys = max(1, len(GEMINI_API_KEYS))
    max_key_rotations = max(num_keys, 3)
    max_network_retries = 3

    for key_attempt in range(max_key_rotations):
        api_key = get_next_key()
        client = genai.Client(api_key=api_key)
        key_num = (key_attempt % num_keys) + 1
        print(f"🔑 Using key #{key_num}")

        for net_retry in range(max_network_retries):
            try:
                for model_name in MODELS_TO_TRY:
                    try:
                        content_parts = []
                        for part in parts:
                            if isinstance(part, str):
                                content_parts.append(part)
                            elif isinstance(part, bytes):
                                content_parts.append(
                                    types.Part.from_bytes(
                                        data=part,
                                        mime_type='image/jpeg'
                                    )
                                )
                            elif isinstance(part, dict) and 'mime_type' in part:
                                content_parts.append(
                                    types.Part.from_bytes(
                                        data=part['data'],
                                        mime_type=part['mime_type']
                                    )
                                )
                            else:
                                content_parts.append(part)

                        response = client.models.generate_content(
                            model=model_name,
                            contents=content_parts,
                            config=types.GenerateContentConfig(
                                system_instruction=system_instruction if system_instruction else None
                            )
                        )

                        print(f"✅ Gemini success — key #{key_num} | model: {model_name}")
                        return response

                    except Exception as model_err:
                        err_str = str(model_err).lower()
                        if '503' in err_str or 'unavailable' in err_str:
                            print(f"⚠️ {model_name} unavailable, trying next model...")
                            continue
                        raise model_err

            except Exception as e:
                last_error = e
                err_str = str(e).lower()

                # Rate limit / Quota exceeded -> rotate to next key
                if any(x in err_str for x in ['429', 'quota', 'rate limit', 'resourceexhausted']):
                    print(f"⚠️ Key #{key_num} hit rate limit → rotating to next key...")
                    break

                # Server 503 unavailable -> backoff & retry
                elif any(x in err_str for x in ['503', 'unavailable']):
                    wait = 2 ** min(net_retry + 1, 3)
                    print(f"⚠️ Gemini service unavailable, retrying in {wait}s (attempt {net_retry + 1}/{max_network_retries})...")
                    time.sleep(wait)
                    continue

                # Temporary network / DNS / connection failure -> backoff & retry
                elif any(x in err_str for x in [
                    'name resolution', 'connecterror', 'connection', 'timeout',
                    'gaierror', 'errno -3', 'errno 101', 'remotedisconnected',
                    'temporary failure'
                ]):
                    wait = 2 ** min(net_retry + 1, 3)
                    print(f"⚠️ Network/DNS connection blip ({e}) → retrying in {wait}s (attempt {net_retry + 1}/{max_network_retries})...")
                    time.sleep(wait)
                    continue

                # Non-retryable error
                else:
                    print(f"❌ Non-retryable error: {e}")
                    raise e

    raise Exception(
        f"Gemini API request failed after multiple retries across all keys. "
        f"Last error: {last_error}. "
        f"Please verify your internet/WiFi connection and DNS settings if name resolution failed."
    )

def get_profile_coords(img, _model_name=None):
    """Ask Gemini for profile photo normalized coordinates"""
    response = call_gemini_with_rotation(
        [img, PROFILE_COORD_PROMPT],
        system_instruction=JSON_SYSTEM_INSTRUCTION
    )
    coords = parse_gemini_json(response.text)
    print(f"📦 Profile coords (normalized): {coords}")
    return coords

def get_qr_coords(img, _model_name=None):
    """Ask Gemini for QR code normalized coordinates"""
    response = call_gemini_with_rotation(
        [img, QR_COORD_PROMPT],
        system_instruction=JSON_SYSTEM_INSTRUCTION
    )
    coords = parse_gemini_json(response.text)
    print(f"📦 QR coords (normalized): {coords}")
    return coords

# ============================================================
# MAIN EXTRACTION — IMAGE MODE (FIXED IMAGE PROCESSING)
# ============================================================

def extract_from_images(front_image, back_image, photo_qr_image):
    """
    Extract all Fayda ID data from 3 images:
    - Text fields
    - Profile photo as base64
    - QR code as base64
    """
    # Open images properly
    front = Image.open(front_image)
    back = Image.open(back_image)

    # Reset file pointer and open photo_qr
    if hasattr(photo_qr_image, 'seek'):
        photo_qr_image.seek(0)
    photo_qr = Image.open(photo_qr_image)
    photo_qr.load()
    img_width, img_height = photo_qr.size
    print(f"📐 photo_qr size: {img_width}x{img_height}")

    # ============================================================
    # FIX: Convert images to RGB and ensure proper format
    # ============================================================
    if front.mode != 'RGB':
        front = front.convert('RGB')
    if back.mode != 'RGB':
        back = back.convert('RGB')
    if photo_qr.mode != 'RGB':
        photo_qr = photo_qr.convert('RGB')
    
    # Convert to bytes with JPEG format (more compatible)
    front_bytes_io = io.BytesIO()
    back_bytes_io = io.BytesIO()
    photo_bytes_io = io.BytesIO()
    
    front.save(front_bytes_io, format='JPEG', quality=90)
    back.save(back_bytes_io, format='JPEG', quality=90)
    photo_qr.save(photo_bytes_io, format='JPEG', quality=90)
    
    front_bytes = front_bytes_io.getvalue()
    back_bytes = back_bytes_io.getvalue()
    photo_bytes = photo_bytes_io.getvalue()
    
    print(f"📏 Front: {len(front_bytes)} bytes, Back: {len(back_bytes)} bytes, Photo: {len(photo_bytes)} bytes")

    # ── Step 1: Extract text fields ──
    print("📝 Extracting text fields...")
    
    # Build parts for the API
    parts = [
        TEXT_EXTRACTION_PROMPT,
        front_bytes,
        back_bytes,
        photo_bytes,
    ]
    
    text_response = call_gemini_with_rotation(
        parts,
        system_instruction=JSON_SYSTEM_INSTRUCTION
    )

    result = parse_gemini_json(text_response.text)

    if 'extracted_texts' not in result:
        raise Exception('Missing extracted_texts in response')

    extracted_texts = result['extracted_texts']
    print(f"✅ Text extracted successfully")

    # ── Step 2: Get profile coordinates and crop ──
    print("👤 Extracting profile image...")
    profile_coords = get_profile_coords(photo_qr)
    profile_crop = crop_image(
        photo_qr,
        profile_coords,
        img_width,
        img_height
    )
    profile_b64 = image_to_base64(profile_crop)
    print(f"✅ Profile extracted successfully")

    # ── Step 3: Get QR coordinates and crop ──
    print("📱 Extracting QR code...")
    qr_coords = get_qr_coords(photo_qr)
    qr_crop = crop_image(
        photo_qr,
        qr_coords,
        img_width,
        img_height
    )
    qr_b64 = image_to_base64(qr_crop)
    print(f"✅ QR extracted successfully")

    return extracted_texts, profile_b64, qr_b64

# ============================================================
# MAIN EXTRACTION — PDF MODE
# ============================================================

def extract_from_pdf(pdf_file):
    """
    Extract all fields from a Fayda ID PDF file.
    Converts PDF page to image first, then uses Gemini to extract.
    """
    import fitz

    print(f"📄 Processing PDF: {pdf_file.filename}")

    # ── Step 1: Convert PDF page 1 to image ──
    try:
        pdf_bytes = pdf_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        page = doc[0]

        mat = fitz.Matrix(300/72, 300/72)
        pix = page.get_pixmap(matrix=mat)

        print(f"📐 PDF page size: {page.rect.width} x {page.rect.height} points")
        print(f"🖼️  Rendered at 300dpi: {pix.width} x {pix.height} pixels")

        img_data = pix.tobytes('png')
        pil_image = Image.open(io.BytesIO(img_data))
        pdf_direct_text = page.get_text("text") or ""
        doc.close()

    except Exception as e:
        raise Exception(f"Failed to convert PDF to image: {str(e)}")

    # ── Step 2: Scale factor ──
    SCALE = 300 / 72

    # ── Step 3: Field coordinates ──
    PDF_FIELD_MAP = {
        "fullNameEnglish":     {"x": 166, "y": 226, "w": 84,  "h": 18},
        "fullNameAmharic":     {"x": 165, "y": 216, "w": 85,  "h": 15},
        "dobGregorian":        {"x": 53,  "y": 290, "w": 66,  "h": 11},
        "dobEthiopian":        {"x": 54,  "y": 280, "w": 54,  "h": 12},
        "genderAmharic":       {"x": 54,  "y": 312, "w": 32,  "h": 15},
        "genderEnglish":       {"x": 54,  "y": 323, "w": 32,  "h": 14},
        "phoneNumber":         {"x": 55,  "y": 377, "w": 57,  "h": 15},
        "subcityAmharic":      {"x": 198, "y": 316, "w": 170, "h": 13},
        "subcityEnglish":      {"x": 197, "y": 325, "w": 170, "h": 14},
        "woredaAmharic":       {"x": 160, "y": 338, "w": 230, "h": 26},
        "woredaEnglish":       {"x": 160, "y": 352, "w": 230, "h": 32},
        "woredaBlock":         {"x": 160, "y": 336, "w": 230, "h": 60},
        "addressBlock":        {"x": 160, "y": 270, "w": 230, "h": 130},
        "regionAmharic":       {"x": 197, "y": 279, "w": 38,  "h": 13},
        "regionEnglish":       {"x": 193, "y": 290, "w": 50,  "h": 10},
        "nationalityAmharic":  {"x": 52,  "y": 344, "w": 73,  "h": 15},
        "nationalityEnglish":  {"x": 54,  "y": 354, "w": 64,  "h": 15},
        "expiryDateGregorian": {"x": 444, "y": 276, "w": 54,  "h": 12},
        "expiryDateEthiopian": {"x": 409, "y": 276, "w": 46,  "h": 11},
        "issueDateGregorian":  {"x": 525, "y": 110, "w": 30,  "h": 80},
        "issueDateEthiopian":  {"x": 525, "y": 160, "w": 30,  "h": 70},
        "FIN":                 {"x": 493, "y": 490, "w": 59,  "h": 15},
        "fanNumber":           {"x": 435, "y": 289, "w": 76,  "h": 24},
    }

    IMAGE_FIELD_MAP = {
        "profilePhoto": {"x": 55,  "y": 100, "w": 86, "h": 120},
        "qrCode":       {"x": 111, "y": 410, "w": 166, "h": 164},
    }

    # ── Step 4: Crop text regions ──
    cropped_regions = {}
    for field_name, coords in PDF_FIELD_MAP.items():
        x1 = int(coords['x'] * SCALE)
        y1 = int(coords['y'] * SCALE)
        x2 = int((coords['x'] + coords['w']) * SCALE)
        y2 = int((coords['y'] + coords['h']) * SCALE)

        padding = 10
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(pil_image.width, x2 + padding)
        y2 = min(pil_image.height, y2 + padding)

        cropped = pil_image.crop((x1, y1, x2, y2))

        if cropped.width < 200:
            scale_up = 200 / cropped.width
            new_w = int(cropped.width * scale_up)
            new_h = int(cropped.height * scale_up)
            cropped = cropped.resize((new_w, new_h), Image.LANCZOS)

        buffer = io.BytesIO()
        cropped.save(buffer, format='PNG')
        cropped_regions[field_name] = base64.b64encode(
            buffer.getvalue()
        ).decode('utf-8')

    # ── Step 5: Crop profile and QR images ──
    profile_b64 = None
    qr_b64 = None

    for field_name, coords in IMAGE_FIELD_MAP.items():
        x1 = int(coords['x'] * SCALE)
        y1 = int(coords['y'] * SCALE)
        x2 = int((coords['x'] + coords['w']) * SCALE)
        y2 = int((coords['y'] + coords['h']) * SCALE)

        cropped = pil_image.crop((x1, y1, x2, y2))
        buffer = io.BytesIO()
        cropped.save(buffer, format='PNG')
        b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        if field_name == 'profilePhoto':
            profile_b64 = b64
        elif field_name == 'qrCode':
            qr_b64 = b64

    # ── Step 6: PDF extraction prompt ──
    PDF_EXTRACTION_PROMPT = """
You are an OCR expert reading cropped regions from an Ethiopian Fayda National ID card PDF.

Each image is a cropped region containing specific fields.
Extract the text accurately and completely. Return ONLY a JSON object.

Rules:
- Return exact text as shown in each image
- For Amharic fields: return the Amharic text exactly
- For dates: keep the exact format shown
- CRITICAL for woredaEnglish: Extract the FULL, COMPLETE name of the Woreda without truncating (e.g. "Gasera", "Woreda 03", "Bole"). NEVER truncate with "..." (no ellipsis) and NEVER cut off ending letters like "ra" (return "Gasera", NEVER "Gase...").
- CRITICAL for woredaAmharic: Extract the FULL, COMPLETE name of the Woreda in Amharic without truncating (e.g. "ጋሰራ", "ወረዳ 03", "ቦሌ"). NEVER truncate with "..." (no ellipsis) and NEVER cut off ending letters like "ራ" (return "ጋሰራ", NEVER "ጋሰ...").
- [Field: woredaBlock] and [Field: addressBlock] show the entire Woreda and Address region. Use them to read the complete words without any cutoff.
- If a field is empty or unreadable: return empty string ""
- Do NOT add any explanation, only JSON

Return this exact JSON structure:
{
  "fullNameAmharic":     "",
  "fullNameEnglish":     "",
  "dobEthiopian":        "",
  "dobGregorian":        "",
  "genderAmharic":       "",
  "genderEnglish":       "",
  "phoneNumber":         "",
  "nationalityAmharic":  "",
  "nationalityEnglish":  "",
  "regionAmharic":       "",
  "regionEnglish":       "",
  "subcityAmharic":      "",
  "subcityEnglish":      "",
  "woredaAmharic":       "",
  "woredaEnglish":       "",
  "issueDateEthiopian":  "",
  "issueDateGregorian":  "",
  "expiryDateEthiopian": "",
  "expiryDateGregorian": "",
  "fin":                 "",
  "fan":                 ""
}
"""

    # ── Step 7: Build Gemini parts ──
    field_order = list(PDF_FIELD_MAP.keys())
    gemini_parts = [PDF_EXTRACTION_PROMPT]

    for field_name in field_order:
        b64 = cropped_regions[field_name]
        img_data = base64.b64decode(b64)
        gemini_parts.append(f"\n[Field: {field_name}]")
        gemini_parts.append({
            "mime_type": "image/png",
            "data": img_data
        })

    # ── Step 8: Call Gemini with rotation ──
    print("🤖 Sending PDF regions to Gemini for OCR...")

    response = call_gemini_with_rotation(
        gemini_parts,
        system_instruction=JSON_SYSTEM_INSTRUCTION
    )

    raw_text = response.text.strip()
    raw_text = re.sub(r'```json\s*', '', raw_text)
    raw_text = re.sub(r'```\s*', '', raw_text)
    raw_text = raw_text.strip()

    extracted = json.loads(raw_text)
    print(f"✅ Gemini PDF response received")

    # ── Post-process and Recover Woreda ──
    raw_am_woreda = extracted.get("woredaAmharic", "").strip()
    raw_en_woreda = extracted.get("woredaEnglish", "").strip()
    print(f"📥 Raw Gemini woreda -> Amharic: '{raw_am_woreda}', English: '{raw_en_woreda}'")

    # 1. Recover full word from direct PDF text if Gemini truncated with ellipsis
    if pdf_direct_text:
        if '...' in raw_en_woreda or '…' in raw_en_woreda or len(raw_en_woreda) < 5:
            prefix = re.sub(r'[\.…]+$', '', raw_en_woreda).strip()
            if prefix and len(prefix) >= 3:
                en_match = re.search(r'\b(' + re.escape(prefix) + r'[a-zA-Z]+)\b', pdf_direct_text, re.IGNORECASE)
                if en_match:
                    raw_en_woreda = en_match.group(1)
                    print(f"📄 Recovered full English Woreda from PDF text: '{raw_en_woreda}'")

        if '...' in raw_am_woreda or '…' in raw_am_woreda or len(raw_am_woreda) < 3:
            prefix_am = re.sub(r'[\.…]+$', '', raw_am_woreda).strip()
            if prefix_am and len(prefix_am) >= 2:
                am_match = re.search(re.escape(prefix_am) + r'[\u1200-\u137F]+', pdf_direct_text)
                if am_match:
                    raw_am_woreda = am_match.group(0)
                    print(f"📄 Recovered full Amharic Woreda from PDF text: '{raw_am_woreda}'")

    # 2. Strip any trailing ellipsis or colon/slash artifacts
    clean_am = re.sub(r'[\.…:]+$', '', raw_am_woreda).strip()
    clean_en = re.sub(r'[\.…:]+$', '', raw_en_woreda).strip()
    clean_am = re.sub(r'^[\.…:]+', '', clean_am).strip()
    clean_en = re.sub(r'^[\.…:]+', '', clean_en).strip()

    # 3. Handle numbered vs named woreda
    am_digits = re.findall(r'\d+', clean_am)
    en_digits = re.findall(r'\d+', clean_en)
    digits = en_digits[0] if en_digits else (am_digits[0] if am_digits else None)

    if digits:
        clean_am_woreda = f"ወረዳ {digits}"
        clean_en_woreda = f"Woreda {digits}"
    else:
        # Named woreda: keep the exact name e.g. "Gasera" and "ጋሰራ"
        clean_am_woreda = clean_am
        clean_en_woreda = clean_en

    print(f"🔍 Final Cleaned Woreda -> Amharic: '{clean_am_woreda}', English: '{clean_en_woreda}'")

    # ── Step 9: Rename keys ──
    extracted_texts = {
        "amharic_name":        extracted.get("fullNameAmharic",     ""),
        "english_name":        extracted.get("fullNameEnglish",     ""),
        "amharic_birth":       extracted.get("dobEthiopian",        ""),
        "english_birth":       extracted.get("dobGregorian",        ""),
        "amharic_sex":         extracted.get("genderAmharic",       ""),
        "english_sex":         extracted.get("genderEnglish",       ""),
        "phone":               extracted.get("phoneNumber",         ""),
        "amharic_region":      extracted.get("regionAmharic",       ""),
        "english_region":      extracted.get("regionEnglish",       ""),
        "amharic_zone":        extracted.get("subcityAmharic",      ""),
        "english_zone":        extracted.get("subcityEnglish",      ""),
        "amharic_woreda":      clean_am_woreda,
        "english_woreda":      clean_en_woreda,
        "fin":                 extracted.get("fin",                 ""),
        "fan":                 extracted.get("fan",                 ""),
        "issueDateEthiopian":  extracted.get("issueDateEthiopian",  ""),
        "issueDateGregorian":  extracted.get("issueDateGregorian",  ""),
        "expiryDateEthiopian": extracted.get("expiryDateEthiopian", ""),
        "expiryDateGregorian": extracted.get("expiryDateGregorian", ""),
    }

    print(f"✅ Extracted {len([v for v in extracted_texts.values() if v])} fields from PDF")
    print(f"📸 Profile image: {'✅' if profile_b64 else '❌'}")
    print(f"📱 QR image: {'✅' if qr_b64 else '❌'}")

    return extracted_texts, profile_b64, qr_b64