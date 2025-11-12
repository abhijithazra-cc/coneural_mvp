from typing import Tuple
import os

def extract_text_from_bytes(filename: str, data: bytes) -> Tuple[str, str]:
    """
    Returns (text, title). For demo we handle plain text & pdf minimal.
    Plug in pypdf/docx2txt etc as you expand.
    """
    name = os.path.basename(filename)
    lower = name.lower()
    if lower.endswith(".txt"):
        return data.decode("utf-8", errors="ignore"), name
    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(data))
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n\n".join(pages), name
        except Exception:
            return "", name
    # default: try utf-8
    return data.decode("utf-8", errors="ignore"), name
