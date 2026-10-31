"""
ocr_engine.py — Layer 2: Tesseract OCR for scanned / image-based PDF pages.

How it works:
  1. Render the PDF page to a PIL Image at OCR_DPI resolution (via pdf2image)
  2. Pre-process the image: grayscale → contrast boost → binarize
  3. Run pytesseract to extract text
  4. Return cleaned text string

Graceful fallback:
  If Tesseract or pdf2image is not installed, this module returns an empty
  string and prints a friendly install hint — the pipeline continues with
  whatever digital text was extracted in Layer 1.

Install:
  pip install pytesseract pdf2image Pillow
  # Windows: also download Tesseract from
  # https://github.com/UB-Mannheim/tesseract/wiki
  # then set TESSERACT_CMD in config.py
"""

import io
import re

from ..config import OCR_DPI, OCR_LANGUAGE, TESSERACT_CMD


# ─────────────────────────────────────────────
# Availability checks (imported lazily)
# ─────────────────────────────────────────────

def _check_tesseract() -> bool:
    """Return True if pytesseract + Tesseract binary are available."""
    try:
        import pytesseract
        if TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _check_pdf2image() -> bool:
    """Return True if pdf2image + poppler are available."""
    try:
        import pdf2image  # noqa: F401
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────────
# Image Pre-processing
# ─────────────────────────────────────────────

def _preprocess_image(pil_image):
    """
    Improve OCR accuracy through image preprocessing:
      • Convert to grayscale
      • Increase contrast using histogram equalization
      • Binarize with a threshold (black/white only)
    """
    try:
        from PIL import ImageEnhance, ImageFilter, ImageOps
        img = pil_image.convert("L")               # grayscale
        img = ImageOps.autocontrast(img)           # stretch contrast
        img = img.filter(ImageFilter.SHARPEN)      # sharpen edges
        # Simple binarize: pixels > 128 → white, else black
        img = img.point(lambda x: 0 if x < 128 else 255, "1")
        return img.convert("RGB")
    except Exception:
        return pil_image  # return original if preprocessing fails


# ─────────────────────────────────────────────
# Core OCR Function
# ─────────────────────────────────────────────

def ocr_page(pdf_bytes: bytes, page_number: int = 1) -> str:
    """
    Run Tesseract OCR on a single PDF page.

    Args:
        pdf_bytes:   Raw PDF bytes (the entire file).
        page_number: 1-indexed page number to OCR.

    Returns:
        Extracted text string, or "" if OCR is unavailable.
    """
    if not _check_pdf2image():
        print("        [OCR] pdf2image not found. Install: pip install pdf2image")
        print("              Also install poppler: https://github.com/oschwartz10612/poppler-windows")
        return ""

    if not _check_tesseract():
        print("        [OCR] Tesseract not found.")
        print("              Install: pip install pytesseract")
        print("              Windows: https://github.com/UB-Mannheim/tesseract/wiki")
        print("              Then set TESSERACT_CMD in pipeline/config.py")
        return ""

    try:
        import pytesseract
        from pdf2image import convert_from_bytes

        # Render only the target page (zero-indexed)
        images = convert_from_bytes(
            pdf_bytes,
            dpi=OCR_DPI,
            first_page=page_number,
            last_page=page_number,
        )

        if not images:
            return ""

        img = _preprocess_image(images[0])

        # Tesseract config: OEM 3 = LSTM, PSM 3 = fully automatic layout
        config = f"--oem 3 --psm 3 -l {OCR_LANGUAGE}"
        raw_text = pytesseract.image_to_string(img, config=config)

        # Clean OCR artefacts
        text = _clean_ocr_output(raw_text)
        return text

    except Exception as e:
        print(f"        [OCR] Error on page {page_number}: {e}")
        return ""


def ocr_image_file(image_path: str) -> str:
    """
    Run Tesseract directly on an image file (PNG, JPEG, TIFF, etc.).
    Useful for image-only documents or screenshots.
    """
    if not _check_tesseract():
        return ""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        img = _preprocess_image(img)
        config = f"--oem 3 --psm 3 -l {OCR_LANGUAGE}"
        raw = pytesseract.image_to_string(img, config=config)
        return _clean_ocr_output(raw)
    except Exception as e:
        print(f"        [OCR] Image OCR error: {e}")
        return ""


# ─────────────────────────────────────────────
# Post-processing
# ─────────────────────────────────────────────

def _clean_ocr_output(text: str) -> str:
    """Remove common OCR artefacts from Tesseract output."""
    if not text:
        return ""
    # Remove form-feed characters
    text = text.replace("\x0c", "\n")
    # Fix ligature artefacts: ﬁ → fi, ﬂ → fl
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("ﬀ", "ff")
    # Remove lines with mostly non-alphabetic chars (OCR noise)
    lines = text.splitlines()
    clean = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        alpha_ratio = sum(c.isalpha() for c in stripped) / max(len(stripped), 1)
        if alpha_ratio > 0.2 or len(stripped) < 5:
            clean.append(stripped)
    text = "\n".join(clean)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
