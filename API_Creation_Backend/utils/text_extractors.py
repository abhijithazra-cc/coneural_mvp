# utils/text_extractors.py
from typing import Optional

def extract_text(file_bytes: bytes, filename: str, mimetype: Optional[str]) -> str:
    """
    Extracts text from common file types: PDF, DOCX, TXT.
    Falls back to UTF-8 decode if extractors fail.
    """
    name = (filename or "").lower()
    mt = (mimetype or "").lower()

    try:
        # PDF
        if name.endswith(".pdf") or "pdf" in mt:
            try:
                import fitz  # PyMuPDF (best)
                from io import BytesIO
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                return "\n".join(p.get_text("text") for p in doc)
            except Exception:
                try:
                    from pypdf import PdfReader
                    from io import BytesIO
                    reader = PdfReader(BytesIO(file_bytes))
                    return "\n".join((p.extract_text() or "") for p in reader.pages)
                except Exception:
                    pass

        # DOCX
        if name.endswith(".docx") or "officedocument.wordprocessingml.document" in mt:
            try:
                import docx
                from io import BytesIO
                d = docx.Document(BytesIO(file_bytes))
                return "\n".join(p.text for p in d.paragraphs)
            except Exception:
                pass

        # Plain text-like
        return file_bytes.decode("utf-8", errors="ignore")

    except Exception:
        return file_bytes.decode("utf-8", errors="ignore")
