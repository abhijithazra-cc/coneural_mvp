# app/utils/chunking.py

import io
from typing import List

from pypdf import PdfReader
import docx  # python-docx
from app.Rag.text_splitters.CharacterSplitter import CharacterSplitter
from app.Rag.text_splitters.SemanticSplitter import SemanticSplitter
from app.Rag.utils import embeddings 
def extract_text_from_file(
    f: io.BytesIO,
    filename: str,
    mime_type: str,
) -> str:
    """
    Extract raw text from PDF / DOCX / TXT.
    You can extend this for more formats later.
    """
    name_lower = filename.lower()

    if name_lower.endswith(".pdf") or mime_type == "application/pdf":
        reader = PdfReader(f)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)

    if name_lower.endswith(".docx") or mime_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        doc = docx.Document(f)
        return "\n".join(p.text for p in doc.paragraphs)

    # fallback: treat as plain text
    data = f.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="ignore")








# def chunk_text(text: str, max_tokens: int = 600, overlap: int = 120) -> List[str]:
#     """
#     Simple approximate chunking by characters.
#     For production, you can swap this out for a tokenizer-aware chunker.
#     """
#     if not text:
#         return []

#     # Very rough char→token approximation
#     approx_chars_per_token = 4
#     max_chars = max_tokens * approx_chars_per_token
#     overlap_chars = overlap * approx_chars_per_token

#     chunks = []
#     start = 0
#     length = len(text)

#     while start < length:
#         end = min(start + max_chars, length)
#         chunk = text[start:end].strip()
#         if chunk:
#             chunks.append(chunk)
#         if end >= length:
#             break
#         start = max(0, end - overlap_chars)

#     return chunks




def chunk_text(docs, max_tokens: int = 1200, overlap: int = 150):
    splitter=SemanticSplitter(embeddings=embeddings)
    chunks=splitter.split_documents(docs=docs,chunk_size=max_tokens,chunk_overlap=overlap)
    return chunks




# ## app/utils/chunking.py
# import io
# import re
# from pypdf import PdfReader
# import docx  # python-docx
# from app.Rag.text_splitters.CharacterSplitter import CharacterSplitter
# from app.Rag.text_splitters.SemanticSplitter import SemanticSplitter
# from app.Rag.utils import embeddings


# # ── Formula extraction helpers ────────────────────────────────────────────────

# def _extract_omml_formula(element) -> str:
#     """
#     Extract Office Math Markup Language (OMML) formulas from a DOCX XML element.
#     Walks the oMath tree and collects run text so the formula is preserved
#     as a readable string instead of being silently dropped.
#     """
#     from lxml import etree

#     MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

#     parts = []
#     for node in element.iter():
#         tag = etree.QName(node).localname if node.tag and "{" in node.tag else node.tag
#         if tag in ("t", "r"):
#             if node.text:
#                 parts.append(node.text.strip())
#         elif tag == "oMathPara":
#             continue

#     formula_text = " ".join(p for p in parts if p)
#     return f"[FORMULA: {formula_text}]" if formula_text else ""


# def _extract_pdf_formulas_pdfminer(f: io.BytesIO) -> str:
#     """
#     Use pdfminer.six for layout-aware text extraction which preserves more
#     mathematical symbols than pypdf's basic extraction.
#     Falls back gracefully if pdfminer is not installed.
#     """
#     try:
#         from pdfminer.high_level import extract_text_to_fp
#         from pdfminer.layout import LAParams

#         out = io.StringIO()
#         laparams = LAParams(
#             line_margin=0.3,
#             word_margin=0.1,
#             char_margin=1.5,
#             detect_vertical=False,
#         )
#         f.seek(0)
#         extract_text_to_fp(f, out, laparams=laparams, output_type="text", codec="utf-8")
#         return out.getvalue()
#     except ImportError:
#         return ""


# def _normalize_formula_text(text: str) -> str:
#     """
#     Light post-processing to make extracted math more readable:
#     - Collapse excessive whitespace inside formula regions
#     - Add spacing around Greek/math unicode so symbols aren't merged into words
#     """
#     text = re.sub(r"\[FORMULA:\s+", "[FORMULA: ", text)

#     math_unicode = re.compile(
#         r"[\u0370-\u03FF"   # Greek
#         r"\u2200-\u22FF"    # Math operators
#         r"\u2070-\u209F"    # Super/subscripts
#         r"\u0300-\u036F]+"  # Combining diacritics
#     )

#     def tag_math(m):
#         sym = m.group(0).strip()
#         return f" {sym} " if sym else ""

#     text = math_unicode.sub(tag_math, text)
#     return text


# # ── Main extraction ───────────────────────────────────────────────────────────

# def extract_text_from_file(
#     f: io.BytesIO,
#     filename: str,
#     mime_type: str,
# ) -> str:
#     """
#     Extract raw text from PDF / DOCX / TXT.
#     Formula-aware: uses pdfminer for PDFs and OMML parsing for DOCX.
#     """
#     name_lower = filename.lower()

#     # ── PDF ──────────────────────────────────────────────────────────────────
#     if name_lower.endswith(".pdf") or mime_type == "application/pdf":
#         # 1. Try pdfminer first – better at preserving math layout
#         f.seek(0)
#         pdfminer_text = _extract_pdf_formulas_pdfminer(f)

#         # 2. Also run pypdf to catch any text pdfminer might miss
#         f.seek(0)
#         reader = PdfReader(f)
#         pypdf_pages = []
#         for page in reader.pages:
#             pypdf_pages.append(page.extract_text() or "")
#         pypdf_text = "\n".join(pypdf_pages)

#         # 3. Prefer pdfminer if it returned substantial content, else fall back
#         raw = pdfminer_text if len(pdfminer_text) > len(pypdf_text) * 0.8 else pypdf_text
#         return _normalize_formula_text(raw)

#     # ── DOCX ─────────────────────────────────────────────────────────────────
#     if name_lower.endswith(".docx") or mime_type in (
#         "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
#     ):
#         f.seek(0)
#         doc = docx.Document(f)
#         parts = []

#         MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

#         for para in doc.paragraphs:
#             math_elements = para._element.findall(f".//{{{MATH_NS}}}oMath")
#             if math_elements:
#                 para_text = para.text
#                 formula_texts = [_extract_omml_formula(el) for el in math_elements]
#                 combined = " ".join(filter(None, [para_text] + formula_texts))
#                 parts.append(combined)
#             else:
#                 if para.text:
#                     parts.append(para.text)

#         # Also scan tables
#         for table in doc.tables:
#             for row in table.rows:
#                 for cell in row.cells:
#                     for para in cell.paragraphs:
#                         if para.text:
#                             parts.append(para.text)

#         raw = "\n".join(parts)
#         return _normalize_formula_text(raw)

#     # ── Plain text fallback ───────────────────────────────────────────────────
#     data = f.read()
#     try:
#         return data.decode("utf-8")
#     except UnicodeDecodeError:
#         return data.decode("latin-1", errors="ignore")


# # ── Chunking ──────────────────────────────────────────────────────────────────

# def chunk_text(docs, max_tokens: int = 500, overlap: int = 100):
#     """
#     Use CharacterSplitter with smaller chunks and overlap so formulas
#     and their surrounding context stay together and are retrievable.
#     SemanticChunker was splitting formula context across chunk boundaries.
#     """
#     splitter = CharacterSplitter(embeddings=embeddings)
#     chunks = splitter.split_documents(docs=docs, chunk_size=max_tokens, chunk_overlap=overlap)
#     return chunks