import os
import traceback
from typing import Optional, Tuple
from PIL import Image

# ============================================================
# CONFIGURATION
# ============================================================
ENABLE_BACKGROUND_REMOVAL = True

# Target dimensions and placement for ID card profile photo
PROFILE_X = 198
PROFILE_Y = 394
PROFILE_WIDTH = 764
PROFILE_HEIGHT = 1039

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_REMBG_HOME = os.path.join(BASE_DIR, "models", "rembg")

if os.path.isdir("/app/models"):
    os.environ["REMBG_HOME"] = "/app/models"
    os.environ["U2NET_HOME"] = "/app/models"
elif os.path.isdir(WORKSPACE_REMBG_HOME):
    os.environ["REMBG_HOME"] = WORKSPACE_REMBG_HOME

# Suppress onnxruntime warnings
os.environ["ORT_LOGGING_LEVEL"] = "3"

_cached_session = None
_cached_model_name: Optional[str] = None


def get_rembg_session():
    """
    Initializes and caches the rembg session.
    Tries 'birefnet-portrait' first, and falls back to 'u2net_human_seg'.
    """
    global _cached_session, _cached_model_name
    if _cached_session is not None:
        return _cached_session, _cached_model_name

    from rembg import new_session

    # Use u2net_human_seg for fast, robust, sub-second local CPU human segmentation
    models_to_try = ["u2net_human_seg", "birefnet-portrait"]
    last_err = None

    for model in models_to_try:
        try:
            print(f"[BG REMOVE] Model: {model}", flush=True)
            session = new_session(model)
            _cached_session = session
            _cached_model_name = model
            return _cached_session, _cached_model_name
        except Exception as exc:
            print(f"[BG REMOVE] Could not initialize model '{model}': {exc}", flush=True)
            last_err = exc

    raise RuntimeError(f"Failed to load any background removal model: {last_err}")


def remove_profile_background(image: Image.Image) -> Image.Image:
    """
    Removes the background from a portrait image using local rembg.
    Returns a transparent PNG (RGBA Image).
    Falls back to the original image on any failure without crashing.
    """
    if not ENABLE_BACKGROUND_REMOVAL:
        return image

    print("[BG REMOVE] Starting background removal...", flush=True)
    try:
        from rembg import remove

        session, model_name = get_rembg_session()

        # Convert to RGBA
        input_rgba = image.convert("RGBA")

        # Run segmentation
        output = remove(input_rgba, session=session)

        if output.mode != "RGBA":
            output = output.convert("RGBA")

        print("[BG REMOVE] Background removal completed", flush=True)
        print("[BG REMOVE] Output image: transparent PNG", flush=True)
        return output

    except Exception as exc:
        print(f"[BG REMOVE] Failed - using original image: {exc}", flush=True)
        traceback.print_exc()
        return image


def fit_portrait_transparent(
    portrait: Image.Image,
    target_width: int = PROFILE_WIDTH,
    target_height: int = PROFILE_HEIGHT
) -> Image.Image:
    """
    Trims unnecessary empty transparent space around the subject,
    preserves person's head, hair, shoulders, clothing, and aspect ratio,
    and fits the portrait neatly into target_width x target_height canvas.
    Never stretches horizontally or vertically.
    """
    portrait_rgba = portrait.convert("RGBA")

    # If image has an alpha channel, trim transparent borders around the subject
    bbox = portrait_rgba.getbbox()
    if bbox is not None:
        trimmed = portrait_rgba.crop(bbox)
    else:
        trimmed = portrait_rgba

    tw, th = trimmed.size
    if tw <= 0 or th <= 0:
        return Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))

    # Calculate scale factor to fit within target box without clipping head or shoulders
    scale = min(target_width / tw, target_height / th)
    new_w = max(1, round(tw * scale))
    new_h = max(1, round(th * scale))

    scaled = trimmed.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Place onto a transparent canvas
    canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))

    # Center horizontally, anchor bottom so bust/shoulders sit naturally at bottom of box
    offset_x = (target_width - new_w) // 2
    offset_y = target_height - new_h

    canvas.alpha_composite(scaled, (offset_x, offset_y))
    return canvas

