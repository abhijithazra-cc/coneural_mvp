import os
import time
import base64
import pickle
import traceback
from pathlib import Path

from celery import Celery, chain
from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_process_init
from sqlalchemy.orm import Session
from langchain_core.documents import Document

from app.database import SessionLocal
from app.models.doc_models import OrgDocument, DocChunk
from app.utils.text_extractors import extract_text
from app.utils.chunking import chunk_text
from app.Rag.CompareDoc import CompareDoc
# CHANGED: no longer import the FAISS-only `vectorManager` singleton or the
# raw `embeddings`/`BASE_DIR` needed to build a FAISS persist_dir by hand.
# Everything backend-specific now lives behind get_vector_manager().
# Adjust these two import paths to wherever you placed VectorManager.py /
# vectorstore_config.py in your tree (e.g. app.Rag.manager.VectorManager,
# app.Rag.manager.vectorstore_config) if different from below.
from app.Rag.VectorManager import get_vector_manager
from app.Rag.Vectorstore_config import configure_vector_manager
from app.Rag.HighlightText import HighlightText
from app.Rag.DocumentConverter import DocumentConverter
from app.Rag.PdfUploader import upload_pdf_to_github  # noqa: F401 (kept for future use)
from app.services.document import _check_duplicate
from app.services.embedding_token import (
    _count_tokens_for_openai_embeddings,
    user_license_and_token_update,
    dept_license_and_token_update,
    org_license_and_token_update,
)

# =========================
# Celery App
# =========================

celery_app = Celery(
    "tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Raised from 300/270 as a stopgap for large document uploads
    # (conversion + minhash + blob insert can legitimately take a while
    # on big PDFs). Use soft limit to fail cleanly with a catchable
    # exception before the hard limit SIGKILLs the worker.
    task_time_limit=600,
    task_soft_time_limit=540,
)

MAX_FILE_BYTES = 100 * 1024 * 1024

# Cap how much text we feed into minhashing. A signature computed on the
# first N chars is still a valid fingerprint for duplicate detection and
# avoids O(n^2)-ish blowups on very large documents.
MINHASH_TEXT_CAP = 50_000

CONVERTED_DIR = Path("app/converted_file")
FILEDATA_DIR = Path("app/filedata")
CITATION_DIR = Path("app/citation_files")


# =========================
# CHANGED: bind the .env-selected vectorstore backend to VectorManager
# once per worker process, not once per task.
#
# Celery's default prefork pool means each worker is a separate OS
# process, and VectorManager is a per-process singleton — so each forked
# worker needs its own factory bound at startup. Without this signal,
# the first call to get_vector_manager() in a task would silently fall
# back to VectorManager's default ("faiss"), regardless of what
# VECTORSTORE_BACKEND says in .env.
# =========================

@worker_process_init.connect
def _init_vector_manager(**kwargs):
    configure_vector_manager()
    print(f"[worker_process_init] vector backend configured from .env (pid={os.getpid()})")


# =========================
# Helpers
# =========================

def _get_doc_by_id(db, org_id, document_id):
    docs = db.query(OrgDocument).filter(
        OrgDocument.org_id == org_id, OrgDocument.id == document_id
    )
    for u in docs:
        print("type u", type(u.file_bytes))
        return u.file_bytes, u.title
    return None, None


# =========================
# Citation / Highlight pipeline
# =========================

def filter_sources_by_citation(citations, org_id, sources):
    cited_files = {c.strip() for c in citations}

    # filename → {document_id, chunks[]}
    grouped = {}

    for src in sources:
        filename = src.get("metadata", {}).get("filename")
        if filename not in cited_files:
            continue

        document_id = src["metadata"]["document_id"]
        chunk = src["page_content"]

        if filename not in grouped:
            grouped[filename] = {"document_id": document_id, "chunks": []}

        grouped[filename]["chunks"].append(chunk)

    output = []
    for filename, data in grouped.items():
        task = helper_filter_sources_by_citation.delay(
            filename, org_id, data["document_id"], data["chunks"]
        )
        output.append({"filename": filename, "link": f"/qa/pdf/{task.id}"})

    return output


@celery_app.task(bind=True)
def helper_filter_sources_by_citation(self, filename, org_id, document_id, chunks):
    """
    Reads the PDF for `document_id`, highlights the given text chunks in it,
    writes the highlighted result to app/citation_files/, and returns the
    base64-encoded PDF.

    Source-of-truth priority for the PDF bytes:
      1. app/converted_file/{filename_stem}.pdf on disk (always a valid PDF,
         written at upload time regardless of original file type)
      2. doc.file_bytes from the DB (LONGBLOB, base64-encoded PDF bytes) as fallback
    """
    db = SessionLocal()
    try:
        doc = db.query(OrgDocument).filter(
            OrgDocument.org_id == org_id,
            OrgDocument.id == document_id,
        ).first()

        if not doc:
            raise ValueError(f"No document found for org_id={org_id}, document_id={document_id}")

        my_bytes = None

        # 1) Prefer the on-disk converted PDF (source of truth)
        if doc.file_path and Path(doc.file_path).exists():
            candidate = Path(doc.file_path).read_bytes()
            if candidate.startswith(b"%PDF"):
                my_bytes = candidate

        # 2) Fallback: try the conventional converted_file location by filename,
        #    in case file_path wasn't populated for this row.
        if not my_bytes:
            pdf_filename = Path(doc.filename).stem + ".pdf"
            fallback_path = CONVERTED_DIR / pdf_filename
            if fallback_path.exists():
                candidate = fallback_path.read_bytes()
                if candidate.startswith(b"%PDF"):
                    my_bytes = candidate

        # 3) Fallback: DB blob (LONGBLOB -> raw bytes, base64-encoded PDF)
        if not my_bytes and doc.file_bytes:
            try:
                candidate = base64.b64decode(bytes(doc.file_bytes))
                if candidate.startswith(b"%PDF"):
                    my_bytes = candidate
            except Exception:
                pass

        if not my_bytes or not my_bytes.startswith(b"%PDF"):
            raise ValueError(
                f"No valid PDF found for document_id={document_id} "
                f"(file_path={doc.file_path!r})"
            )

        obj = HighlightText()
        my_bytes, pages = obj.highlight_text(my_bytes, chunks=chunks)

        task_id = self.request.id
        pages_str = "_".join(str(n) for n in pages)
        output_path = CITATION_DIR / f"{task_id}@{pages_str}.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(my_bytes)

        print(f"PDF written to {output_path}")

        return {
            "filename": doc.title,
            "pdf": base64.b64encode(my_bytes).decode("utf-8"),
            "document_id": document_id,
            "link": "link_placeholder",
            "pages": pages,
        }
    finally:
        db.close()


# =========================
# Upload pipeline
# =========================

@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_kwargs={"max_retries": 3},
)
def extract_and_store_doc_task(
    self,
    payload: bytes,
    original_filename: str,
    filename: str,
    content_type: str,
    org_id: int,
    dept_id: int | None,
    user_id: int,
    tag: str,
    doc_scope: str,
):
    """
    1. Extracts text from the uploaded file (any supported type).
    2. Ensures a PDF version of the file exists:
         - if the upload was already a PDF, use it as-is
         - otherwise, convert it to PDF
    3. Always writes that final PDF to app/converted_file/{filename_stem}.pdf
       so there is a single reliable on-disk source of truth for the PDF,
       regardless of what the original upload format was.
    4. Stores the PDF bytes (base64-encoded) in OrgDocument.file_bytes (LONGBLOB)
       and the disk path in OrgDocument.file_path.

    Includes timing instrumentation (printed to worker logs) so slow steps
    are visible instead of the task just hitting the hard time limit and
    getting SIGKILLed with no context.
    """
    db: Session = SessionLocal()
    try:
        if not payload:
            raise ValueError("Empty file")
        if len(payload) > MAX_FILE_BYTES:
            raise ValueError("File too large")

        # ---- Extract text ----
        t0 = time.monotonic()
        text, docs = extract_text(
            payload,
            filename=filename,
            mimetype=content_type or "",
        )
        print(f"[TIMING] extract_text: {time.monotonic() - t0:.2f}s (text_len={len(text)})")

        # ---- Duplicate check ----
        # NOTE: unchanged — this is a separate, DB/minhash-based dup check
        # (_check_duplicate), independent of the vectorstore's own
        # is_similar_document(). Both exist for different reasons: this one
        # runs before any embedding call to save the cost entirely; the
        # vectorstore one is a secondary check on the actual chunk vectors.
        t0 = time.monotonic()
        _check_duplicate(
            db=db,
            org_id=org_id,
            dept_id=dept_id,
            new_text=text.lower(),
            threshold=0.8,
        )
        print(f"[TIMING] _check_duplicate: {time.monotonic() - t0:.2f}s")

        # ---- Ensure PDF bytes ----
        file_ext = Path(original_filename).suffix.lower()
        t0 = time.monotonic()

        if file_ext == ".pdf":
            # Already a PDF — use as-is
            stored_payload = payload
        else:
            # Convert to PDF first
            print("Its not pdf, converting to pdf before storing")
            doc_converter = DocumentConverter()
            stored_payload = doc_converter.convert_to_pdf_bytes(
                file_bytes=payload,
                filename=original_filename,
                extracted_text=text,
            )
        print(f"[TIMING] pdf conversion: {time.monotonic() - t0:.2f}s")

        if not stored_payload or not stored_payload.startswith(b"%PDF"):
            raise ValueError(
                f"Conversion did not produce a valid PDF for {original_filename} "
                f"(len={len(stored_payload) if stored_payload else 0})"
            )

        # ---- Write PDF to disk (source of truth) ----
        t0 = time.monotonic()
        pdf_filename = Path(filename).stem + ".pdf"
        CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
        converted_path = CONVERTED_DIR / pdf_filename
        converted_path.write_bytes(stored_payload)
        print(f"[TIMING] write pdf to disk: {time.monotonic() - t0:.2f}s -> {converted_path}")

        # ---- Minhash (capped input to avoid pathological slowness) ----
        t0 = time.monotonic()
        compdoc = CompareDoc()
        minhash_input = text[:MINHASH_TEXT_CAP]
        doc_hash = pickle.dumps(compdoc.create_minhash(minhash_input))
        print(f"[TIMING] minhash: {time.monotonic() - t0:.2f}s (input_len={len(minhash_input)})")

        # ---- Build + commit DB row ----
        t0 = time.monotonic()
        doc = OrgDocument(
            org_id=org_id,
            dept_id=None if doc_scope == "global" else dept_id,
            uploaded_by=user_id,
            title=original_filename,
            tag=tag,
            scope=doc_scope,
            filename=filename,
            mime_type="application/pdf",
            size_bytes=len(stored_payload),
            file_path=str(converted_path),                  # disk source of truth
            file_bytes=base64.b64encode(stored_payload),     # LONGBLOB: raw bytes is correct
            hash_bytes=doc_hash,
        )

        db.add(doc)
        db.commit()
        db.refresh(doc)
        print(f"[TIMING] db commit: {time.monotonic() - t0:.2f}s (doc_id={doc.id})")

        serializable_docs = [
            {"page_content": d.page_content, "metadata": d.metadata}
            for d in docs
        ]

        return {
            "user_id": user_id,
            "doc_id": doc.id,
            "docs": serializable_docs,
            "org_id": org_id,
            "dept_id": dept_id,
            "scope": doc_scope,
        }

    except SoftTimeLimitExceeded:
        db.rollback()
        print(
            f"[TIMEOUT] extract_and_store_doc_task soft time limit hit for "
            f"{original_filename} (task_id={self.request.id})"
        )
        raise

    except Exception:
        db.rollback()
        traceback.print_exc()
        raise
    finally:
        db.close()


@celery_app.task
def chunk_and_store_task(payload: dict):
    db: Session = SessionLocal()
    try:
        docs = [
            Document(page_content=d["page_content"], metadata=d["metadata"])
            for d in payload["docs"]
        ]

        chunks = chunk_text(docs=docs, max_tokens=512, overlap=120)
        if not chunks:
            raise ValueError("No chunks extracted")

        db.add_all(
            [
                DocChunk(document_id=payload["doc_id"], content=chunk.page_content)
                for chunk in chunks
            ]
        )
        db.commit()

        return {
            "doc_id": payload["doc_id"],
            "chunks": [
                {"page_content": c.page_content, "metadata": c.metadata} for c in chunks
            ],
            "user_id": payload["user_id"],
            "org_id": payload["org_id"],
            "dept_id": payload["dept_id"],
            "scope": payload["scope"],
        }
    finally:
        db.close()


@celery_app.task(time_limit=180)
def embed_and_index_task(payload: dict):
    db: Session = SessionLocal()
    try:
        # CHANGED: was —
        #   vs = vectorManager.get_store(
        #       embeddings=embeddings,
        #       persist_dir=f"{BASE_DIR}/{payload['org_id']}",
        #   )
        # which hardcoded FAISS and built its persist_dir by hand.
        #
        # Now: org_id is the only thing this task provides. Which backend
        # (faiss/pinecone/qdrant) it resolves to, and how that backend
        # turns org_id into a directory/index/collection, was already
        # decided at worker startup by _init_vector_manager() reading
        # .env — this task doesn't know or care.
        manager = get_vector_manager()
        org_id = str(payload["org_id"])  # vectorstore constructors require org_id as str
        vs = manager.get_store(org_id)

        documents = [
            Document(page_content=chunk["page_content"], metadata=chunk["metadata"])
            for chunk in payload["chunks"]
        ]

        # CHANGED: stringify dept_id for consistency with how it's written
        # everywhere else (metadata equality filters are string-based —
        # mixing int/str here would silently break dept-scoped search).
        dept_id = str(payload["dept_id"]) if payload["scope"] == "department" else "global"

        vs.add_documents(
            documents=documents,
            document_id=payload["doc_id"],
            dept_id=dept_id,
        )

        token_count = sum(
            _count_tokens_for_openai_embeddings(
                model_name="text-embedding-ada-002",
                texts=[chunk["page_content"]],
            )
            for chunk in payload["chunks"]
        )

        user_license_and_token_update(db, payload["user_id"], token_count)
        org_license_and_token_update(db, payload["org_id"], token_count)

        db.commit()
        return {"status": "success", "doc_id": payload["doc_id"]}
    finally:
        db.close()


@celery_app.task
def upload_file_to_db_task(
    payload: bytes,
    original_filename: str,
    filename,
    content_type: str,
    org_id: int,
    dept_id: int | None,
    user_id: int,
    tag: str,
    doc_scope: str,
):
    return chain(
        extract_and_store_doc_task.s(
            payload,
            original_filename,
            filename,
            content_type,
            org_id,
            dept_id,
            user_id,
            tag,
            doc_scope,
        ),
        chunk_and_store_task.s(),
        embed_and_index_task.s(),
    ).apply_async()