"""
Text extraction with smart routing:
- PDF: try direct text extraction (PyMuPDF) first — fast for digital invoices.
  Fall back to PaddleOCR only if extracted text is too short (scanned PDF).
- Images (JPG, PNG): always use PaddleOCR.

PaddleOCR instance is lazy-loaded to avoid slow startup on every request.
"""
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np
from PIL import Image

# Skip slow HuggingFace connectivity check
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

if TYPE_CHECKING:
    from paddleocr import PaddleOCR as _PaddleOCRType

_ocr_instance: Optional["_PaddleOCRType"] = None

# Minimum chars extracted via direct PDF text before we trust it (skip OCR)
_MIN_TEXT_LENGTH = 100


def _get_ocr() -> "_PaddleOCRType":
    global _ocr_instance
    if _ocr_instance is None:
        from paddleocr import PaddleOCR
        _ocr_instance = PaddleOCR()
    return _ocr_instance


def _ocr_image(image: Image.Image) -> str:
    """Run PaddleOCR on a PIL Image, return plain text."""
    results = _get_ocr().predict(np.array(image))
    lines: list[str] = []
    for result in results:
        texts = result.get("rec_texts", [])
        scores = result.get("rec_scores", [])
        for text, score in zip(texts, scores):
            if score > 0.3 and text.strip():
                lines.append(text.strip())
    return "\n".join(lines)


def _extract_pdf_direct(file_path: str) -> str:
    """Extract text directly from PDF (works for digital/vector PDFs)."""
    import fitz
    doc = fitz.open(file_path)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    return "\n\n".join(pages)


def _extract_pdf_ocr(file_path: str) -> str:
    """Render each PDF page and OCR it (for scanned PDFs)."""
    import fitz
    doc = fitz.open(file_path)
    pages: list[str] = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        pages.append(_ocr_image(img))
    return "\n\n".join(pages)


def extract_text(file_path: str) -> str:
    """
    Extract text from PDF or image.
    PDFs: direct extraction first, OCR fallback for scans.
    Images: OCR always.
    """
    suffix = Path(file_path).suffix.lower()

    if suffix == ".pdf":
        text = _extract_pdf_direct(file_path)
        if len(text.strip()) >= _MIN_TEXT_LENGTH:
            return text  # digital PDF — fast path
        # Scanned PDF — fall back to OCR
        return _extract_pdf_ocr(file_path)

    if suffix in (".jpg", ".jpeg", ".png"):
        img = Image.open(file_path).convert("RGB")
        return _ocr_image(img)

    raise ValueError(f"Unsupported file type: {suffix}")
