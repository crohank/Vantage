"""
PDF Extractor

Extracts text from PDF documents for RAG ingestion.
"""

import io
from typing import Optional


def extract_pdf_text(file_path: str) -> Optional[str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        print("[PDF Extractor] pypdf not installed. Install with: pip install pypdf")
        return None

    try:
        reader = PdfReader(file_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())

        if not pages:
            return None
        return "\n\n".join(pages)
    except Exception as e:
        print(f"[PDF Extractor] Failed to extract PDF text: {e}")
        return None


def extract_pdf_bytes(content: bytes) -> Optional[str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        print("[PDF Extractor] pypdf not installed. Install with: pip install pypdf")
        return None

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())
        return "\n\n".join(pages) if pages else None
    except Exception as e:
        print(f"[PDF Extractor] Failed to extract PDF bytes: {e}")
        return None
