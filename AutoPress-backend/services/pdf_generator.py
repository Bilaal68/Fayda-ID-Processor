import os
import io
import base64
import random
import traceback
from typing import Dict, Any, Optional, Tuple, List, Set

from PIL import Image, ImageDraw, ImageFont, ImageOps
import fitz

from services.bg_remover import (
    remove_profile_background,
    fit_portrait_transparent,
    ENABLE_BACKGROUND_REMOVAL,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_template_path(name: str) -> str:
    """Find template path supporting exact name or leading space in filename."""
    p1 = os.path.join(BASE_DIR, "templates", name)
    if os.path.exists(p1):
        return p1
    p2 = os.path.join(BASE_DIR, "templates", " " + name)
    if os.path.exists(p2):
        return p2
    return p1


FRONT_TEMPLATE_PATH = resolve_template_path("id_front.png")
BACK_TEMPLATE_PATH = resolve_template_path("id_back.png")


# ============================================================
# CONSTANTS & PHYSICAL DIMENSIONS
# ============================================================

CARD_WIDTH_MM = 85.60
CARD_HEIGHT_MM = 53.98
PRINT_DPI = 300

CARD_PRINT_WIDTH_PX = round(CARD_WIDTH_MM / 25.4 * PRINT_DPI)    # 1011
CARD_PRINT_HEIGHT_PX = round(CARD_HEIGHT_MM / 25.4 * PRINT_DPI)  # 638

A4_WIDTH_MM = 210
A4_HEIGHT_MM = 297

A4_WIDTH_PX = round(A4_WIDTH_MM / 25.4 * PRINT_DPI)              # 2480
A4_HEIGHT_PX = round(A4_HEIGHT_MM / 25.4 * PRINT_DPI)            # 3508

MASTER_WIDTH = 2610
MASTER_HEIGHT = 1650

# Backwards compatibility constants
CARD_WIDTH = MASTER_WIDTH
CARD_HEIGHT = MASTER_HEIGHT
A4_WIDTH = A4_WIDTH_PX
A4_HEIGHT = A4_HEIGHT_PX
A4_DPI = PRINT_DPI


# ============================================================
AMHARIC_FONT_PATH = os.path.join(BASE_DIR, "fonts", "NotoSansEthiopic-Bold.ttf")
ENGLISH_FONT_PATH = os.path.join(BASE_DIR, "fonts", "Roboto-Bold.ttf")
BOLD_FONT_PATH = os.path.join(BASE_DIR, "fonts", "Roboto-Bold.ttf")

FONT_CANDIDATES = [
    os.path.join(BASE_DIR, "fonts", "NotoSansEthiopic-Bold.ttf"),
    os.path.join(BASE_DIR, "fonts", "Roboto-Bold.ttf"),
    "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Bold.ttf",
]


# ============================================================
# FRONT FIELDS (Relative to 2610x1650 Master Canvas)
# ============================================================

FRONT_FIELDS = {
    "fullNameAmharic": {
        "x": 1041, "y": 476, "width": 800, "height": 98,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "fullNameEnglish": {
        "x": 1039, "y": 597, "width": 800, "height": 126,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "dobEthiopian": {
        "x": 1041, "y": 806, "width": 800, "height": 103,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "dobGregorian": {
        "x": 1041, "y": 806, "width": 800, "height": 103,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "genderAmharic": {
        "x": 1039, "y": 965, "width": 800, "height": 103,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "genderEnglish": {
        "x": 1039, "y": 965, "width": 800, "height": 103,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "issueDate": {
        "x": 35, "y": 320, "width": 80, "height": 381,
        "fontSize": 75, "rotation": 90, "align": "center", "type": "text"
    },

    "issueDateAmharic": {
        "x": 35, "y": 1016, "width": 80, "height": 329,
        "fontSize": 75, "rotation": 90, "align": "center", "type": "text"
    },

    "expiryDateAmharic": {
        "x": 1036, "y": 1145, "width": 800, "height": 131,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "expiryDate": {
        "x": 1036, "y": 1145, "width": 800, "height": 131,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "profilePhoto": {
        "x": 198, "y": 394, "width": 764, "height": 1039,
        "fontSize": 24, "rotation": 0, "type": "image"
    },

    "smallProfile": {
        "x": 2116, "y": 1194, "width": 247, "height": 298,
        "fontSize": 24, "rotation": 0, "type": "image"
    },

    "barcode": {
        "x": 1178, "y": 1304, "width": 725, "height": 239,
        "fontSize": 200, "rotation": 0, "type": "barcode"
    }
}


# ============================================================
# BACK FIELDS (Relative to 2610x1650 Master Canvas)
# ============================================================

BACK_FIELDS = {
    "phoneNumber": {
        "x": 60, "y": 170, "width": 700, "height": 105,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "nationalityAmharic": {
        "x": 60, "y": 412, "width": 800, "height": 115,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "nationalityEnglish": {
        "x": 60, "y": 412, "width": 800, "height": 115,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "text"
    },

    "regionAmharic": {
        "x": 60, "y": 608, "width": 700, "height": 82,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "address_stack"
    },

    "regionEnglish": {
        "x": 60, "y": 608, "width": 700, "height": 82,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "address_stack"
    },

    "subcityAmharic": {
        "x": 60, "y": 608, "width": 700, "height": 82,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "address_stack"
    },

    "subcityEnglish": {
        "x": 60, "y": 608, "width": 700, "height": 82,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "address_stack"
    },

    "woredaAmharic": {
        "x": 60, "y": 608, "width": 700, "height": 82,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "address_stack"
    },

    "woredaEnglish": {
        "x": 60, "y": 608, "width": 700, "height": 82,
        "fontSize": 75, "rotation": 0, "align": "left", "type": "address_stack"
    },

    "FIN": {
        "x": 330, "y": 1361, "width": 514, "height": 40,
        "fontSize": 60, "rotation": 0, "align": "left", "type": "text"
    },

    "serialNumber": {
        "x": 2095, "y": 1505, "width": 401, "height": 40,
        "fontSize": 80, "rotation": 0, "align": "center", "type": "text"
    },

    "QR": {
        "x": 1167, "y": 73, "width": 1360, "height": 1380,
        "fontSize": 210, "rotation": 0, "type": "qr"
    }
}


# ============================================================
# DATA MAPPING & ALIASES
# ============================================================

DATA_KEY_MAP = {
    "fullNameAmharic": "fullNameAmharic",
    "fullNameEnglish": "fullNameEnglish",

    "dobEthiopian": "dobEthiopian",
    "dobGregorian": "dobGregorian",

    "genderAmharic": "genderAmharic",
    "genderEnglish": "genderEnglish",

    "issueDate": "issueDateGregorian",
    "issueDateAmharic": "issueDateEthiopian",

    "expiryDate": "expiryDateGregorian",
    "expiryDateAmharic": "expiryDateEthiopian",

    "phoneNumber": "phoneNumber",

    "nationalityAmharic": "nationalityAmharic",
    "nationalityEnglish": "nationalityEnglish",

    "regionAmharic": "regionAmharic",
    "regionEnglish": "regionEnglish",

    "subcityAmharic": "subcityAmharic",
    "subcityEnglish": "subcityEnglish",

    "woredaAmharic": "woredaAmharic",
    "woredaEnglish": "woredaEnglish",

    "FIN": "fin",
    "serialNumber": "serialNumber",
}

AMHARIC_FIELDS = {
    "fullNameAmharic",
    "dobEthiopian",
    "genderAmharic",
    "issueDateAmharic",
    "expiryDateAmharic",
    "nationalityAmharic",
    "regionAmharic",
    "subcityAmharic",
    "woredaAmharic",
}

FIELD_ALIASES = {
    "fullNameAmharic": ["fullNameAmharic", "amharic_name"],
    "fullNameEnglish": ["fullNameEnglish", "english_name"],
    "dobEthiopian": ["dobEthiopian", "amharic_birth"],
    "dobGregorian": ["dobGregorian", "english_birth"],
    "genderAmharic": ["genderAmharic", "amharic_sex"],
    "genderEnglish": ["genderEnglish", "english_sex"],
    "issueDate": ["issueDate", "issueDateGregorian"],
    "issueDateAmharic": ["issueDateAmharic", "issueDateEthiopian"],
    "expiryDate": ["expiryDate", "expiryDateGregorian"],
    "expiryDateAmharic": ["expiryDateAmharic", "expiryDateEthiopian"],
    "phoneNumber": ["phoneNumber", "phone"],
    "nationalityAmharic": ["nationalityAmharic", "ኢትዮጵያዊ"],
    "nationalityEnglish": ["nationalityEnglish", "Ethiopian"],
    "regionAmharic": ["regionAmharic", "amharic_region"],
    "regionEnglish": ["regionEnglish", "english_region"],
    "subcityAmharic": ["subcityAmharic", "amharic_zone"],
    "subcityEnglish": ["subcityEnglish", "english_zone"],
    "woredaAmharic": ["woredaAmharic", "amharic_woreda"],
    "woredaEnglish": ["woredaEnglish", "english_woreda"],
    "FIN": ["FIN", "fin"],
    "serialNumber": ["serialNumber"],
}


# ============================================================
# BASE64 HELPER
# ============================================================

def base64_to_pil(data) -> Optional[Image.Image]:
    if not data:
        return None

    if isinstance(data, Image.Image):
        return data.copy().convert("RGBA")

    try:
        if isinstance(data, bytes):
            raw = data
        elif isinstance(data, str):
            if data.startswith("data:") and "," in data:
                data = data.split(",", 1)[1]
            raw = base64.b64decode(data)
        else:
            return None

        return Image.open(io.BytesIO(raw)).convert("RGBA")

    except Exception as exc:
        print(f"❌ Image decode failed: {type(exc).__name__}: {exc}", flush=True)
        return None


# ============================================================
# IMAGE FIT
# ============================================================

def fit_image(
    image: Image.Image,
    width: int,
    height: int,
    contain: bool = False
) -> Image.Image:
    image = image.convert("RGBA")

    if contain:
        fitted = ImageOps.contain(
            image,
            (width, height),
            method=Image.Resampling.LANCZOS
        )
        canvas = Image.new(
            "RGBA",
            (width, height),
            (255, 255, 255, 0)
        )
        canvas.alpha_composite(
            fitted,
            (
                (width - fitted.width) // 2,
                (height - fitted.height) // 2
            )
        )
        return canvas

    return ImageOps.fit(
        image,
        (width, height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )


# ============================================================
# FONT HANDLING
# ============================================================

def load_font(
    size: int,
    is_amharic: bool = False,
    bold: bool = True
) -> ImageFont.FreeTypeFont:
    path = AMHARIC_FONT_PATH if is_amharic else ENGLISH_FONT_PATH
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass

    for candidate in FONT_CANDIDATES:
        if os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                pass

    return ImageFont.load_default()


def is_ethiopic_char(ch: str) -> bool:
    cp = ord(ch)
    return (0x1200 <= cp <= 0x137F) or (0x1380 <= cp <= 0x139F) or (0x2D80 <= cp <= 0x2DDF) or (0xAB00 <= cp <= 0xAB2F)


def get_text_segments(text: str) -> List[Tuple[str, bool]]:
    if not text:
        return []
    segments: List[Tuple[str, bool]] = []
    curr_str: List[str] = []
    curr_is_eth = None

    for ch in text:
        ch_is_eth = is_ethiopic_char(ch)
        if curr_is_eth is None:
            curr_is_eth = ch_is_eth
            curr_str.append(ch)
        elif ch_is_eth == curr_is_eth:
            curr_str.append(ch)
        else:
            segments.append(("".join(curr_str), curr_is_eth))
            curr_str = [ch]
            curr_is_eth = ch_is_eth

    if curr_str:
        segments.append(("".join(curr_str), curr_is_eth if curr_is_eth is not None else False))
    return segments


def measure_multiscript_text(draw: ImageDraw.ImageDraw, text: str, font_size: int) -> Tuple[int, int]:
    font_eth = load_font(font_size, is_amharic=True, bold=True)
    font_rob = load_font(font_size, is_amharic=False, bold=True)
    segments = get_text_segments(text)
    total_w = 0
    max_h = 0
    for seg_text, is_eth in segments:
        f = font_eth if is_eth else font_rob
        bbox = draw.textbbox((0, 0), seg_text, font=f)
        total_w += (bbox[2] - bbox[0])
        max_h = max(max_h, bbox[3] - bbox[1])
    return total_w, max_h


def render_multiscript_text(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font_size: int,
    fill=(0, 0, 0, 255)
) -> Tuple[int, int]:
    font_eth = load_font(font_size, is_amharic=True, bold=True)
    font_rob = load_font(font_size, is_amharic=False, bold=True)
    segments = get_text_segments(text)
    cx = x
    total_w = 0
    max_h = 0
    for seg_text, is_eth in segments:
        f = font_eth if is_eth else font_rob
        draw.text((cx, y), seg_text, font=f, fill=fill)
        bbox = draw.textbbox((cx, y), seg_text, font=f)
        seg_w = (bbox[2] - bbox[0])
        seg_h = (bbox[3] - bbox[1])
        cx += seg_w
        total_w += seg_w
        max_h = max(max_h, seg_h)
    return total_w, max_h


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])


def get_fitting_font_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    starting_size: int,
    minimum_size: int = 10
) -> int:
    size = max(int(starting_size), minimum_size)
    while size >= minimum_size:
        w, h = measure_multiscript_text(draw, text, size)
        if w <= max_width and h <= max_height:
            return size
        size -= 1
    return minimum_size


def get_fitting_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    starting_size: int,
    is_amharic: bool = False,
    minimum_size: int = 10
):
    size = get_fitting_font_size(draw, text, max_width, max_height, starting_size, minimum_size)
    return load_font(size, is_amharic=is_amharic, bold=True)


# ============================================================
# FIELD VALUE RETRIEVAL
# ============================================================

def get_field_value(
    card_data: Dict[str, Any],
    field_name: str
) -> str:
    mapped = DATA_KEY_MAP.get(field_name, field_name)

    edited = card_data.get("edited_texts", {}) or {}
    extracted = card_data.get("extracted_texts", {}) or {}

    keys_to_try = [mapped, field_name]
    if field_name in FIELD_ALIASES:
        for alias in FIELD_ALIASES[field_name]:
            if alias not in keys_to_try:
                keys_to_try.append(alias)

    for k in keys_to_try:
        if k in edited and edited[k] not in (None, ""):
            return str(edited[k]).strip()

    for k in keys_to_try:
        if k in extracted and extracted[k] not in (None, ""):
            return str(extracted[k]).strip()

    for k in keys_to_try:
        if k in card_data and card_data[k] not in (None, ""):
            return str(card_data[k]).strip()

    if field_name == "nationalityAmharic":
        return "ኢትዮጵያዊ"
    if field_name == "nationalityEnglish":
        return "Ethiopian"

    return ""


# ============================================================
# FIN FORMATTER
# ============================================================

def format_fin(value: str) -> str:
    if not value:
        return ""
    clean = "".join(c for c in str(value) if c.isalnum())
    if len(clean) in (12, 16):
        return " ".join([clean[i:i + 4] for i in range(0, len(clean), 4)])
    return str(value).strip()


PAIRED_TEXT_FIELDS = {
    "dobEthiopian": ("dobGregorian", "dob"),
    "dobGregorian": ("dobEthiopian", "dob"),
    "genderAmharic": ("genderEnglish", "gender"),
    "genderEnglish": ("genderAmharic", "gender"),
    "expiryDateAmharic": ("expiryDate", "expiryDate"),
    "expiryDate": ("expiryDateAmharic", "expiryDate"),
    "nationalityAmharic": ("nationalityEnglish", "nationality"),
    "nationalityEnglish": ("nationalityAmharic", "nationality"),
}



# ============================================================
# ADDRESS STACK RENDERER
# Renders Region / Subcity / Woreda lines tightly packed
# with no large gaps between them.
# ============================================================

ADDRESS_STACK_GROUPS = [
    ("regionAmharic",  "regionEnglish"),
    ("subcityAmharic", "subcityEnglish"),
    ("woredaAmharic",  "woredaEnglish"),
]

def draw_address_stack(
    image: Image.Image,
    fields: Dict[str, Any],
    card_data: Dict[str, Any],
):
    """
    Renders the 6 address fields as 3 paired groups:
      regionAmharic / regionEnglish
      [group gap]
      subcityAmharic / subcityEnglish
      [group gap]
      woredaAmharic / woredaEnglish

    Within each pair lines are tightly packed (small inner gap).
    Between groups there is a larger separator gap.
    """
    draw = ImageDraw.Draw(image)

    start_x   = 60
    start_y   = 608
    max_width = 700
    font_size = 75
    inner_gap = 10   # px between Amharic and English within the same field
    group_gap = 50   # px between Region / Subcity / Woreda groups

    current_y = start_y

    for group_index, (amharic_key, english_key) in enumerate(ADDRESS_STACK_GROUPS):
        # Add group gap before every group except the first
        if group_index > 0:
            current_y += group_gap

        for field_name in (amharic_key, english_key):
            value = get_field_value(card_data, field_name)
            if not value:
                continue

            fit_size = get_fitting_font_size(
                draw, value, max_width, font_size, font_size
            )

            tw, th = measure_multiscript_text(draw, value, fit_size)
            render_multiscript_text(draw, start_x, current_y, value, fit_size, fill=(0, 0, 0, 255))

            current_y += th + inner_gap


# ============================================================
# DRAW TEXT FIELD
# ============================================================

def draw_text_field(
    image: Image.Image,
    field_name: str,
    field: Dict[str, Any],
    card_data: Dict[str, Any],
    rendered_pairs: Optional[Set[str]] = None
):
    if rendered_pairs is None:
        rendered_pairs = set()

    # 1. Handle paired fields (e.g. dobEthiopian | dobGregorian)
    if field_name in PAIRED_TEXT_FIELDS:
        peer_name, group_id = PAIRED_TEXT_FIELDS[field_name]
        if group_id in rendered_pairs:
            return  # already rendered as part of this pair
        rendered_pairs.add(group_id)

        first_key, second_key = (field_name, peer_name) if field_name in (
            "dobEthiopian", "genderAmharic", "expiryDateAmharic", "nationalityAmharic"
        ) else (peer_name, field_name)

        val1 = get_field_value(card_data, first_key)
        val2 = get_field_value(card_data, second_key)

        if val1 and val2:
            if "|" in val1 or "|" in val2:
                if "|" in val1 and "|" in val2:
                    value = val1
                elif "|" in val1:
                    value = val1 if val2 in val1 else f"{val1} {val2}".strip()
                else:
                    value = val2 if val1 in val2 else f"{val1} {val2}".strip()
            else:
                value = f"{val1} | {val2}"
        elif val1:
            value = val1
        elif val2:
            value = val2
        else:
            return
    else:
        value = get_field_value(card_data, field_name)
        if field_name == "serialNumber":
            # Always generate a fresh random 8-digit serial number —
            # never copy or derive it from the FIN.
            value = str(random.randint(10_000_000, 99_999_999))
        elif not value:
            return

    if field_name == "issueDateAmharic":
        value = value.replace("|", "").strip()

    if field_name == "FIN":
        value = format_fin(value)

    draw = ImageDraw.Draw(image)

    x = int(field["x"])
    y = int(field["y"])
    width = int(field["width"])
    height = int(field["height"])
    rotation = int(field.get("rotation", 0))
    align = field.get("align", "left")


    if rotation in (90, 270):
        fit_w, fit_h = height, width
    else:
        fit_w, fit_h = width, height

    fit_size = get_fitting_font_size(
        draw,
        value,
        fit_w,
        fit_h,
        int(field.get("fontSize", 52))
    )

    text_width, text_height = measure_multiscript_text(draw, value, fit_size)

    if align == "center":
        tx = x + max(0, (width - text_width) // 2)
    elif align == "right":
        tx = x + max(0, width - text_width)
    else:  # left
        tx = x
    ty = y + max(0, (height - text_height) // 2)

    if rotation == 0:
        render_multiscript_text(draw, tx, ty, value, fit_size, fill=(0, 0, 0, 255))
        return

    layer = Image.new(
        "RGBA",
        (text_width + 40, text_height + 40),
        (255, 255, 255, 0)
    )
    layer_draw = ImageDraw.Draw(layer)
    render_multiscript_text(layer_draw, 20, 20, value, fit_size, fill=(0, 0, 0, 255))

    rotated = layer.rotate(
        rotation,
        expand=True,
        resample=Image.Resampling.BICUBIC
    )

    image.alpha_composite(
        rotated,
        (
            x + max(0, (width - rotated.width) // 2),
            y + max(0, (height - rotated.height) // 2)
        )
    )


# ============================================================
# DRAW PROFILE / IMAGE FIELD
# ============================================================

def draw_image_field(
    image: Image.Image,
    field_name: str,
    field: Dict[str, Any],
    card_data: Dict[str, Any]
):
    extracted = card_data.get("extracted_texts", {}) or {}
    edited = card_data.get("edited_texts", {}) or {}

    source = (
        card_data.get("profile_image")
        or card_data.get("profile_b64")
        or card_data.get("profileImage")
        or edited.get("profile_image")
        or edited.get("profile_b64")
        or extracted.get("profile_image")
        or extracted.get("profile_b64")
    )

    if not source:
        return

    profile = base64_to_pil(source)
    if profile is None:
        return

    if card_data.get("use_black_and_white"):
        profile = profile.convert("L").convert("RGBA")

    x = int(field["x"])
    y = int(field["y"])
    width = int(field["width"])
    height = int(field["height"])

    if field_name == "profilePhoto":
        if ENABLE_BACKGROUND_REMOVAL:
            # Check if this card already has the processed profile photo cached
            processed = card_data.get("_processed_profile")
            if processed is None:
                processed = remove_profile_background(profile)
                card_data["_processed_profile"] = processed
            fitted = fit_portrait_transparent(processed, width, height)
        else:
            fitted = fit_image(profile, width, height, contain=False)
        image.alpha_composite(fitted, (x, y))
    elif field_name == "smallProfile":
        # Safely reuse the processed portrait if available, maintaining existing dimensions
        source_img = card_data.get("_processed_profile", profile)
        fitted = fit_image(source_img, width, height, contain=False)
        image.alpha_composite(fitted, (x, y))
    else:
        fitted = fit_image(profile, width, height, contain=False)
        image.alpha_composite(fitted, (x, y))


# ============================================================
# BARCODE GENERATION & DRAWING
# ============================================================

def generate_barcode(
    value: str,
    width: int,
    height: int
) -> Optional[Image.Image]:
    if not value:
        return None

    try:
        import barcode
        from barcode.writer import ImageWriter

        code = barcode.get("code128", str(value), writer=ImageWriter())
        buffer = io.BytesIO()

        code.write(
            buffer,
            options={
                "write_text": False,
                "module_width": 0.35,
                "module_height": 14,
                "quiet_zone": 2
            }
        )

        buffer.seek(0)
        generated = Image.open(buffer).convert("RGBA")
        bars_crop = generated.crop(generated.getbbox())
        bars_fitted = bars_crop.resize((int(width), int(height)), Image.Resampling.LANCZOS)
        return bars_fitted

    except Exception as exc:
        print(f"❌ Barcode error: {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
        return None


def draw_barcode_field(
    image: Image.Image,
    field_name: str,
    field: Dict[str, Any],
    card_data: Dict[str, Any]
):
    extracted = card_data.get("extracted_texts", {}) or {}
    edited = card_data.get("edited_texts", {}) or {}

    # Barcode data should use fan and fall back to fin only — never serialNumber
    value = (
        edited.get("fan")
        or extracted.get("fan")
        or card_data.get("fan")
        or edited.get("fin")
        or extracted.get("fin")
        or card_data.get("fin")
        or get_field_value(card_data, "FIN")
    )

    if not value:
        return

    fan_str = "".join(c for c in str(value) if c.isalnum())
    if not fan_str:
        return

    box_x = int(field["x"])
    box_y = int(field["y"])
    box_w = int(field["width"])
    box_h = int(field["height"])

    draw = ImageDraw.Draw(image)

    bar_width = min(box_w - 40, 660)
    bx = box_x + max(0, (box_w - bar_width) // 2)

    # 1. Draw FAN number centered above the barcode
    # Dynamically fit the font so all digits are fully visible and readable
    target_text_w = int(bar_width * 0.96)
    max_text_h = 52
    font_size = 68
    while font_size >= 24:
        font = load_font(font_size, is_amharic=False, bold=True)
        tw, th = text_size(draw, fan_str, font)
        if tw <= target_text_w and th <= max_text_h:
            break
        font_size -= 1

    tx = bx + max(0, (bar_width - tw) // 2)
    ty = box_y - 10

    t_bbox = draw.textbbox((tx, ty), fan_str, font=font)
    draw.text((tx, ty), fan_str, font=font, fill=(0, 0, 0, 255))

    # 2. Draw barcode bars below FAN text
    bar_top = t_bbox[3] + 16
    bar_height = max(50, (box_y + box_h) - bar_top - 10)

    barcode_image = generate_barcode(
        fan_str,
        int(bar_width),
        int(bar_height)
    )

    if barcode_image is None:
        return

    image.paste(
        barcode_image,
        (bx, bar_top),
        barcode_image
    )


# ============================================================
# QR CODE FIELD
# ============================================================

def draw_qr_field(
    image: Image.Image,
    field_name: str,
    field: Dict[str, Any],
    card_data: Dict[str, Any]
):
    extracted = card_data.get("extracted_texts", {}) or {}
    edited = card_data.get("edited_texts", {}) or {}

    source = (
        card_data.get("qr_image")
        or card_data.get("qr_b64")
        or card_data.get("qrImage")
        or card_data.get("QR")
        or edited.get("qr_image")
        or edited.get("qr_b64")
        or edited.get("QR")
        or extracted.get("qr_image")
        or extracted.get("qr_b64")
        or extracted.get("QR")
    )

    if not source:
        return

    qr = base64_to_pil(source)
    if qr is None:
        return

    box_w = int(field["width"])
    box_h = int(field["height"])
    box_x = int(field["x"])
    box_y = int(field["y"])

    # QR codes are square — use the smaller dimension so it fits inside the box
    qr_size = min(box_w, box_h)

    # Scale to fill the square area exactly (no padding)
    qr_scaled = qr.convert("RGBA").resize(
        (qr_size, qr_size),
        Image.Resampling.LANCZOS
    )

    # Place on a white canvas the full box size, centered
    canvas = Image.new("RGBA", (box_w, box_h), (255, 255, 255, 255))
    offset_x = (box_w - qr_size) // 2
    offset_y = (box_h - qr_size) // 2
    canvas.alpha_composite(qr_scaled, (offset_x, offset_y))

    image.alpha_composite(canvas, (box_x, box_y))


_TEMPLATE_CACHE: Dict[str, Image.Image] = {}

def load_template(path: str, side: str) -> Image.Image:
    if path in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[path].copy()

    print(f"📂 Loading {side} template: {path}", flush=True)

    if not os.path.exists(path):
        raise FileNotFoundError(f"{side} template not found: {path}")

    image = Image.open(path).convert("RGBA")
    _TEMPLATE_CACHE[path] = image
    print(f"✅ {side} template loaded and cached: {image.width}x{image.height}", flush=True)
    return image.copy()


def validate_fields(
    fields: Dict[str, Any],
    image_width: int,
    image_height: int,
    side: str
):
    for name, field in fields.items():
        x = int(field["x"])
        y = int(field["y"])
        width = int(field["width"])
        height = int(field["height"])

        if x < 0 or y < 0:
            raise ValueError(f"{side}.{name}: negative coordinates")
        if width <= 0 or height <= 0:
            raise ValueError(f"{side}.{name}: invalid size")
        if x + width > image_width:
            raise ValueError(f"{side}.{name}: exceeds template width ({x + width} > {image_width})")
        if y + height > image_height:
            raise ValueError(f"{side}.{name}: exceeds template height ({y + height} > {image_height})")


# ============================================================
# RENDER SINGLE CARD SIDE (2610x1650 Master Canvas)
# ============================================================

def render_card_side(
    template_path: str,
    fields: Dict[str, Any],
    card_data: Dict[str, Any],
    side_name: str
) -> Image.Image:
    print(f"🪪 Rendering {side_name}", flush=True)

    template = load_template(template_path, side_name)
    validate_fields(fields, template.width, template.height, side_name)

    result = template.copy().convert("RGBA")
    rendered_pairs: Set[str] = set()
    address_stack_drawn = False  # draw the address stack only once

    for field_name, field in fields.items():
        try:
            field_type = field.get("type", "text")

            if field_type == "address_stack":
                if not address_stack_drawn:
                    draw_address_stack(result, fields, card_data)
                    address_stack_drawn = True
            elif field_type == "text":
                draw_text_field(result, field_name, field, card_data, rendered_pairs)
            elif field_type == "image":
                draw_image_field(result, field_name, field, card_data)
            elif field_type == "barcode":
                draw_barcode_field(result, field_name, field, card_data)
            elif field_type in ("qr", "QR"):
                draw_qr_field(result, field_name, field, card_data)

        except Exception as exc:
            print(f"❌ Failed {side_name}.{field_name}: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            raise

    print(f"✅ {side_name} complete", flush=True)
    return result


# ============================================================
# RENDER COMPLETE ID CARD (Master -> Print Resize)
# ============================================================

def render_complete_card(card_data: Dict[str, Any]) -> Dict[str, Image.Image]:
    """
    Renders complete front and back card at 2610x1650 master size,
    then downsamples to 1011x638 print size using Lanczos.
    """
    print("\n========================================", flush=True)
    print("🪪 RENDERING COMPLETE ID CARD", flush=True)
    print("========================================", flush=True)

    rendered_front = render_card_side(
        FRONT_TEMPLATE_PATH,
        FRONT_FIELDS,
        card_data,
        "FRONT"
    )

    rendered_back = render_card_side(
        BACK_TEMPLATE_PATH,
        BACK_FIELDS,
        card_data,
        "BACK"
    )

    # ── Strict Master Dimensions Verification ──
    if rendered_front.size != (MASTER_WIDTH, MASTER_HEIGHT):
        raise ValueError(
            f"rendered_front size {rendered_front.size} != {(MASTER_WIDTH, MASTER_HEIGHT)}"
        )
    if rendered_back.size != (MASTER_WIDTH, MASTER_HEIGHT):
        raise ValueError(
            f"rendered_back size {rendered_back.size} != {(MASTER_WIDTH, MASTER_HEIGHT)}"
        )

    print(f"MASTER CARD: {MASTER_WIDTH}x{MASTER_HEIGHT}", flush=True)

    # ── Downsample to 300 DPI Print Size (1011x638) using Lanczos ──
    print_front = rendered_front.resize(
        (CARD_PRINT_WIDTH_PX, CARD_PRINT_HEIGHT_PX),
        Image.Resampling.LANCZOS
    )
    print_back = rendered_back.resize(
        (CARD_PRINT_WIDTH_PX, CARD_PRINT_HEIGHT_PX),
        Image.Resampling.LANCZOS
    )

    # ── Strict Print Dimensions Verification ──
    if print_front.size != (CARD_PRINT_WIDTH_PX, CARD_PRINT_HEIGHT_PX):
        raise ValueError(
            f"print_front size {print_front.size} != {(CARD_PRINT_WIDTH_PX, CARD_PRINT_HEIGHT_PX)}"
        )
    if print_back.size != (CARD_PRINT_WIDTH_PX, CARD_PRINT_HEIGHT_PX):
        raise ValueError(
            f"print_back size {print_back.size} != {(CARD_PRINT_WIDTH_PX, CARD_PRINT_HEIGHT_PX)}"
        )

    print(f"PRINT CARD: {CARD_PRINT_WIDTH_PX}x{CARD_PRINT_HEIGHT_PX} @ {PRINT_DPI} DPI", flush=True)

    # Free master resolution canvases immediately to save memory
    del rendered_front
    del rendered_back

    return {
        "front": print_front,
        "back": print_back,
    }


# ============================================================
# PNG BYTES
# ============================================================

def pil_to_png_bytes(image: Image.Image, dpi: int = PRINT_DPI) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", dpi=(dpi, dpi))
    return buffer.getvalue()


# ============================================================
# DYNAMIC A4 CARD POSITIONS (Exact 1011x638 at 300 DPI)
# Kept as-is — still used by generate_single_card_pdf for
# single front-only / back-only output.
# ============================================================

def get_a4_card_positions(card_count: int) -> List[Tuple[int, int, int, int]]:
    """
    Calculate card positions dynamically based on the number of cards.
    Every card placed on A4 remains exactly 1011 x 638 pixels at 300 DPI.
    Front and back sheets use the exact same positions so they correspond.
    Cards are arranged in up to 2 columns and centered on the A4 page.
    """
    if card_count <= 0:
        return []

    card_w = CARD_PRINT_WIDTH_PX  # 1011
    card_h = CARD_PRINT_HEIGHT_PX # 638
    gap_x = 80
    gap_y = 60

    if card_count == 1:
        cols = 1
        rows = 1
    else:
        cols = 2
        rows = (card_count + cols - 1) // cols

    total_grid_w = cols * card_w + (cols - 1) * gap_x
    total_grid_h = rows * card_h + (rows - 1) * gap_y

    margin_x = (A4_WIDTH_PX - total_grid_w) // 2
    margin_y = (A4_HEIGHT_PX - total_grid_h) // 2

    positions = []
    for index in range(card_count):
        if cols == 1:
            col = 0
            row = 0
        else:
            col = index % cols
            row = index // cols

        x = int(margin_x + col * (card_w + gap_x))
        y = int(margin_y + row * (card_h + gap_y))
        positions.append((x, y, card_w, card_h))

    return positions


# ============================================================
# A4 SHEET COMPOSITION (2480x3508 at 300 DPI)
# Kept as-is — still used by generate_single_card_pdf for
# single front-only / back-only output.
# ============================================================

def create_a4_sheet(
    rendered_cards: List[Dict[str, Any]],
    side: str,
    positions: List[Tuple[int, int, int, int]]
) -> Image.Image:
    sheet = Image.new("RGB", (A4_WIDTH_PX, A4_HEIGHT_PX), "white")

    # ── Strict A4 Canvas Verification ──
    if sheet.size != (A4_WIDTH_PX, A4_HEIGHT_PX):
        raise ValueError(
            f"a4_canvas size {sheet.size} != {(A4_WIDTH_PX, A4_HEIGHT_PX)}"
        )

    print(f"A4: {A4_WIDTH_PX}x{A4_HEIGHT_PX} @ {PRINT_DPI} DPI", flush=True)

    for index, card in enumerate(rendered_cards):
        x, y, width, height = positions[index]
        print(f"CARD {index + 1} POSITION: x={x}, y={y}", flush=True)

        card_img = card[side]
        if card_img.size != (CARD_PRINT_WIDTH_PX, CARD_PRINT_HEIGHT_PX):
            raise ValueError(
                f"Card {index + 1} {side} size {card_img.size} != {(CARD_PRINT_WIDTH_PX, CARD_PRINT_HEIGHT_PX)}"
            )

        # Paste directly without any further resizing
        sheet.paste(card_img.convert("RGB"), (x, y))

    return sheet


# ============================================================
# A4 FRONT+BACK PAIR POSITIONS — anchored to the TOP of the page
# (front beside back, per card, no vertical centering / no gap
# above card 1). This is the layout generate_final_pdf uses.
# ============================================================

PAIR_GAP_X = 80    # gap between front and back of the same card
ROW_GAP_Y = 60      # gap between different cards' rows
TOP_MARGIN_Y = 39    # space above card 1 — 0 means it starts right at the page edge


def get_a4_pair_positions(card_count: int) -> List[Dict[str, Any]]:
    """
    Returns one entry per card:
      {
        "page": <0-based page index>,
        "front": (x, y, w, h),
        "back":  (x, y, w, h),
      }
    Front and back sit side by side; each card is its own row.
    Rows start from the TOP of the page (TOP_MARGIN_Y), not
    vertically centered — card 1 sits at the very top.
    Horizontally centered. Auto-paginates if more cards than
    fit on one page.
    """
    if card_count <= 0:
        return []

    card_w = CARD_PRINT_WIDTH_PX
    card_h = CARD_PRINT_HEIGHT_PX
    pair_w = card_w * 2 + PAIR_GAP_X
    pair_h = card_h

    max_rows_per_page = max(
        1,
        (A4_HEIGHT_PX - TOP_MARGIN_Y + ROW_GAP_Y) // (pair_h + ROW_GAP_Y)
    )

    margin_x = (A4_WIDTH_PX - pair_w) // 2

    positions = []
    for i in range(card_count):
        page_index = i // max_rows_per_page
        row_in_page = i % max_rows_per_page

        y = TOP_MARGIN_Y + row_in_page * (pair_h + ROW_GAP_Y)
        front_x = margin_x
        back_x = margin_x + card_w + PAIR_GAP_X

        positions.append({
            "page": page_index,
            "front": (front_x, y, card_w, card_h),
            "back": (back_x, y, card_w, card_h),
        })

    return positions


MIRROR_CARDS_FOR_PRINTING = True  # Reverse/mirror print for PVC film lamination


def create_a4_pair_sheets(
    rendered_cards: List[Dict[str, Any]],
    positions: List[Dict[str, Any]],
    mirror: bool = MIRROR_CARDS_FOR_PRINTING
) -> List[Image.Image]:
    """
    Builds one A4 PIL image per page. On each page, every card's
    front and back are pasted side by side in their assigned row.
    When mirror=True (PVC film lamination mode):
      - Both front and back are mirrored horizontally (FLIP_LEFT_RIGHT)
      - The back is placed on the left, and the front on the right
    """
    if not positions:
        return []

    num_pages = max(p["page"] for p in positions) + 1
    sheets = []

    for page_num in range(num_pages):
        sheet = Image.new("RGB", (A4_WIDTH_PX, A4_HEIGHT_PX), "white")

        if sheet.size != (A4_WIDTH_PX, A4_HEIGHT_PX):
            raise ValueError(
                f"a4_canvas size {sheet.size} != {(A4_WIDTH_PX, A4_HEIGHT_PX)}"
            )

        print(f"A4 PAGE {page_num + 1}: {A4_WIDTH_PX}x{A4_HEIGHT_PX} @ {PRINT_DPI} DPI (mirror={mirror})", flush=True)

        for idx, pos in enumerate(positions):
            if pos["page"] != page_num:
                continue

            card = rendered_cards[idx]
            fx, fy, fw, fh = pos["front"]
            bx, by, bw, bh = pos["back"]

            front_img = card["front"]
            back_img = card["back"]

            for img, size in ((front_img, (fw, fh)), (back_img, (bw, bh))):
                if img.size != size:
                    raise ValueError(
                        f"Card {idx + 1} image size {img.size} != {size}"
                    )

            if mirror:
                # Mirror horizontally for PVC transfer / sublimation printing
                front_mirrored = front_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                back_mirrored = back_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

                print(f"  CARD {idx + 1} (MIRRORED): back=({fx},{fy}) front=({bx},{by})", flush=True)
                sheet.paste(back_mirrored.convert("RGB"), (fx, fy))
                sheet.paste(front_mirrored.convert("RGB"), (bx, by))
            else:
                print(f"  CARD {idx + 1}: front=({fx},{fy}) back=({bx},{by})", flush=True)
                sheet.paste(front_img.convert("RGB"), (fx, fy))
                sheet.paste(back_img.convert("RGB"), (bx, by))

        sheets.append(sheet)

    return sheets


# ============================================================
# A4 RASTER TO PDF (Exact 595.2756 x 841.8898 pt)
# ============================================================

def a4_image_to_pdf(images: List[Image.Image]) -> bytes:
    """
    Converts A4 PIL Images (2480x3508 at 300 DPI) into an exact physical
    A4 PDF page (210 x 297 mm -> 595.2756 x 841.8898 points).
    """
    document = fitz.open()

    try:
        # Exact A4 in points: 210mm / 25.4 * 72 = 595.2756 pt, 297mm / 25.4 * 72 = 841.8898 pt
        page_width_pt = 595.2756
        page_height_pt = 841.8898
        print(f"PDF PAGE: {page_width_pt} x {page_height_pt} pt", flush=True)

        for image in images:
            png_bytes = pil_to_png_bytes(image, dpi=PRINT_DPI)

            page = document.new_page(
                width=page_width_pt,
                height=page_height_pt
            )

            # Insert raster to fill the entire physical A4 page
            page.insert_image(
                page.rect,
                stream=png_bytes
            )

        return document.tobytes(deflate=True, garbage=4)

    finally:
        document.close()


# ============================================================
# ============================================================
# MAIN FINAL PNG GENERATOR (300 DPI A4 SHEET)
# ============================================================

def generate_final_png(
    cards_data: List[Dict[str, Any]],
    template_count: Optional[int] = None
) -> bytes:
    print("\n========================================", flush=True)
    print("🚀 STARTING ID PNG GENERATION (300 DPI)", flush=True)
    print(f"🪪 Cards: {len(cards_data)}", flush=True)
    print(f"MASTER CARD: {MASTER_WIDTH}x{MASTER_HEIGHT}", flush=True)
    print(f"PRINT CARD: {CARD_PRINT_WIDTH_PX}x{CARD_PRINT_HEIGHT_PX} @ {PRINT_DPI} DPI", flush=True)
    print(f"A4: {A4_WIDTH_PX}x{A4_HEIGHT_PX} @ {PRINT_DPI} DPI", flush=True)
    print("========================================", flush=True)

    if not cards_data:
        raise ValueError("No card data supplied.")

    rendered_cards = []

    for index, card_data in enumerate(cards_data):
        print(f"\n🃏 Preparing card {index + 1}/{len(cards_data)}", flush=True)

        try:
            rendered = render_complete_card(card_data)
            rendered_cards.append(rendered)
            if "_processed_profile" in card_data:
                del card_data["_processed_profile"]
            import gc
            gc.collect()
        except Exception as exc:
            print(f"❌ Card {index + 1} failed: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            raise

    # Front+back side by side, one card per row, starting at the top,
    # auto-paginated
    positions = get_a4_pair_positions(len(rendered_cards))
    pages = create_a4_pair_sheets(rendered_cards, positions)

    # Convert the primary A4 sheet (2480x3508) to lossless 300 DPI PNG bytes
    png_bytes = pil_to_png_bytes(pages[0], dpi=PRINT_DPI)

    print("\n========================================", flush=True)
    print("✅ FINAL ID PNG GENERATED", flush=True)
    print(f"📐 Sheet dimensions: {pages[0].width}x{pages[0].height} @ {PRINT_DPI} DPI", flush=True)
    print(f"📦 PNG size: {len(png_bytes):,} bytes", flush=True)
    print("========================================", flush=True)

    return png_bytes


# Alias generate_final_pdf to return the high-quality output
def generate_final_pdf(
    cards_data: List[Dict[str, Any]],
    template_count: Optional[int] = None
) -> bytes:
    # When output is requested as PNG, route directly to generate_final_png
    return generate_final_png(cards_data, template_count)


# ============================================================
# SINGLE CARD PDF (FOR PREVIEWS OR INDIVIDUAL PRINTS)
# Unchanged.
# ============================================================

def generate_single_card_pdf(
    card_data: Dict[str, Any],
    side: str = "both"
) -> bytes:
    if side not in ("front", "back", "both"):
        raise ValueError("side must be 'front', 'back', or 'both'")

    rendered = render_complete_card(card_data)
    positions = get_a4_card_positions(1)

    sheets = []
    if side in ("front", "both"):
        sheets.append(create_a4_sheet([rendered], "front", positions))
    if side in ("back", "both"):
        sheets.append(create_a4_sheet([rendered], "back", positions))

    return a4_image_to_pdf(sheets)


# ============================================================
# PREVIEW
# ============================================================

def generate_card_preview(
    card_data: Dict[str, Any],
    side: str = "front"
) -> bytes:
    if side not in ("front", "back"):
        raise ValueError("side must be 'front' or 'back'")

    rendered = render_complete_card(card_data)
    return pil_to_png_bytes(rendered[side])