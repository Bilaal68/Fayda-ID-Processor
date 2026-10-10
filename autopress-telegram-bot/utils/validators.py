"""
Input and File Validators

Validation helper functions for incoming documents, file sizes,
MIME types, and PDF magic byte headers.
"""

from typing import Optional, Tuple
from config import settings


def validate_pdf_metadata(
    file_name: Optional[str],
    file_size: Optional[int],
    mime_type: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate that an uploaded document metadata represents a valid PDF within size limits.
    Returns (is_valid, error_message).
    """
    if not file_name or not file_name.lower().endswith(".pdf"):
        return False, "File must be a valid PDF document (.pdf)."

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size and file_size > max_bytes:
        return False, f"File size exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB limit."

    if mime_type and mime_type not in ("application/pdf", "application/octet-stream", "application/x-pdf"):
        return False, f"Invalid MIME type: {mime_type}. Please send a PDF document."

    return True, None


def validate_pdf_bytes(data: bytes) -> Tuple[bool, Optional[str]]:
    """
    Deep validation of PDF content by verifying magic header bytes and minimum length.
    Returns (is_valid, error_message).
    """
    if not data or len(data) < 32:
        return False, "The uploaded file is empty or corrupted."

    # Standard PDF files start with %PDF- (0x25 0x50 0x44 0x46 0x2D)
    # Some generators have a UTF-8 BOM or leading whitespace
    header = data[:1024].lstrip(b"\xef\xbb\xbf\r\n\t ")
    if not header.startswith(b"%PDF-"):
        return False, "The uploaded file is not a valid PDF document."

    return True, None
