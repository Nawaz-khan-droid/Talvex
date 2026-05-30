#!/usr/bin/env python3
"""
TALVEX Resume Text Extraction Script

Extracts text from PDF files using a cascading fallback strategy:
  1. PyPDF2 (fast, works for text-based PDFs)
  2. pdfminer (better text extraction)
  3. OCR via pdf2image + pytesseract (for scanned/image-based PDFs)

Usage:
  python3 scripts/extract_resume.py <file_path>

Output (JSON to stdout):
  {"extractedText": "...", "ocrUsed": false, "wordCount": 123}

Exit codes:
  0 - Success
  1 - File not found or invalid arguments
  2 - Extraction failed (all methods exhausted)
"""

import json
import os
import re
import sys


def is_valid_extracted_text(text: str, min_words: int = 20) -> bool:
    """Check if extracted text is actual readable content, not raw PDF binary."""
    if not text or len(text.strip()) < 50:
        return False
    # Raw PDF binary starts with %PDF
    if text.strip().startswith("%PDF"):
        return False
    # Check if it has enough alphabetic characters (binary has mostly symbols)
    alpha_count = sum(1 for c in text if c.isalpha() or c.isspace())
    ratio = alpha_count / max(1, len(text))
    if ratio < 0.5:
        return False
    # Check for minimum word count of real words
    words = [w for w in text.split() if any(c.isalpha() for c in w)]
    return len(words) >= min_words


def extract_text_pdf(file_path: str):
    """
    Extract text from PDF with cascading fallback.
    Returns (extracted_text, ocr_used) or raises on total failure.
    """
    # Ensure PATH has tesseract
    os.environ['PATH'] = '/usr/bin:/usr/local/bin:/home/z/.local/bin:' + os.environ.get('PATH', '')

    # Attempt 1: PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        if is_valid_extracted_text(text):
            return text.strip(), False
    except Exception:
        pass

    # Attempt 2: pdfminer
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(file_path)
        if is_valid_extracted_text(text):
            return text.strip(), False
    except Exception:
        pass

    # Attempt 3: OCR via pdf2image + pytesseract
    try:
        from pdf2image import convert_from_path
        import pytesseract

        images = convert_from_path(file_path, dpi=300)
        text = ""
        for img in images:
            text += pytesseract.image_to_string(img) + "\n"
        text = text.strip()

        if is_valid_extracted_text(text):
            return text, True
    except Exception as e:
        # Log to stderr so it doesn't corrupt JSON stdout
        print(f"OCR extraction failed: {e}", file=sys.stderr)

    raise RuntimeError(
        "Failed to extract text from PDF. The file may be corrupted or image-based with no readable text."
    )


def extract_text_txt(file_path: str):
    """Extract text from a .txt file."""
    encodings = ["utf-8", "latin-1", "ascii", "utf-16"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc, errors="replace") as f:
                text = f.read()
            if text.strip():
                return text.strip()
        except Exception:
            continue
    return ""


def extract_text_docx(file_path: str):
    """Extract text from a .docx file using mammoth."""
    try:
        import mammoth
        with open(file_path, "rb") as f:
            result = mammoth.extract_raw_text(f)
            return result.value.strip()
    except ImportError:
        print("mammoth not installed for docx, falling back to text", file=sys.stderr)
        return extract_text_txt(file_path)
    except Exception as e:
        print(f"docx extraction failed: {e}, falling back to text", file=sys.stderr)
        return extract_text_txt(file_path)


def main():
    if len(sys.argv) < 2:
        print(
            json.dumps({"error": "Usage: python3 extract_resume.py <file_path>"}),
            file=sys.stdout,
        )
        sys.exit(1)

    file_path = sys.argv[1]

    if not os.path.isfile(file_path):
        print(
            json.dumps({"error": f"File not found: {file_path}"}),
            file=sys.stdout,
        )
        sys.exit(1)

    # Determine file type from extension
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "txt"

    try:
        if ext == "txt":
            extracted_text = extract_text_txt(file_path)
            ocr_used = False
        elif ext == "docx":
            extracted_text = extract_text_docx(file_path)
            ocr_used = False
        elif ext == "pdf":
            extracted_text, ocr_used = extract_text_pdf(file_path)
        else:
            # Fallback: try txt extraction
            extracted_text = extract_text_txt(file_path)
            ocr_used = False

        word_count = len(extracted_text.split())

        result = {
            "extractedText": extracted_text,
            "ocrUsed": ocr_used,
            "wordCount": word_count,
        }

        print(json.dumps(result), file=sys.stdout)
        sys.exit(0)

    except Exception as e:
        print(
            json.dumps({"error": str(e)}),
            file=sys.stdout,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
