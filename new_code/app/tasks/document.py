
from app.utils.celery_app import celery_app
from app.services.document import _ensure_org_admin,_ensure_org_admin_or_dept_admin_or_author,_ensure_can_manage_global_docs,_ensure_can_manage_dept_docs,_ensure_same_org,_check_duplicate
from app.database import SessionLocal
import base64, pickle, time, traceback
from sqlalchemy.orm import Session
from celery import shared_task
@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10, retry_kwargs={"max_retries": 3})
def upload_file_to_db_task(
    self,
    file_path: str,
    original_filename: str,
    content_type: str,
    org_id: int,
    dept_id: int | None,
    user_id: int,
    tag: str,
    doc_scope: str,
):
    db: Session = SessionLocal()

    try:
        # 1) Read file
        with open(file_path, "rb") as f:
            payload = f.read()

        if not payload:
            raise ValueError("Empty file")

        if len(payload) > MAX_FILE_BYTES:
            raise ValueError("File too large")

        # 2) Extract text
        filename = f"{org_id}_{user_id}_{int(time.time())}_{original_filename}"

        text, docs = extract_text(
            payload,
            filename=filename,
            mimetype=content_type or "",
        )

        new_text = text.lower()

        duplicate = _check_duplicate(
            db=db,
            org_id=org_id,
            dept_id=dept_id,
            new_text=new_text,
            threshold=0.8,
        )

        # 3) Minhash
        compdoc = CompareDoc()
        m = compdoc.create_minhash(text)
        doc_hash = pickle.dumps(m)

        # 4) Chunking
        chunks = chunk_text(docs=docs, max_tokens=512, overlap=120)
        if not chunks:
            raise ValueError("No chunks extracted")

        # 5) Store document
        doc_bytes = base64.b64encode(payload)

        doc = OrgDocument(
            org_id=org_id,
            dept_id=None if doc_scope == "global" else dept_id,
            uploaded_by=user_id,
            title=original_filename,
            tag=tag,
            scope=doc_scope,
            filename=filename,
            mime_type=content_type or "application/octet-stream",
            size_bytes=len(payload),
            file_bytes=doc_bytes,
            hash_bytes=doc_hash,
        )

        db.add(doc)
        db.flush()  # get doc.id

        # 6) Vector store
        vs = vectorManager.get_store(
            embeddings=embeddings,
            persist_dir=f"{BASE_DIR}/{org_id}",
        )

        vs.add_documents(
            documents=chunks,
            document_id=doc.id,
            dept_id=dept_id if doc_scope == "department" else "global",
        )

        # 7) Token accounting
        token = sum(
            _count_tokens_for_openai_embeddings(
                model_name="text-embedding-ada-002",
                texts=[chunk.page_content],
            )
            for chunk in chunks
        )

        if dept_id and doc_scope == "department":
            user_license_and_token_update(db, user_id, dept_id, token)
            dept_license_and_token_update(db, dept_id, org_id, token)
        else:
            org_license_and_token_update(db, org_id, token)

        # 8) Save chunks
        db.add_all(
            [
                DocChunk(document_id=doc.id, content=chunk.page_content)
                for chunk in chunks
            ]
        )

        db.commit()
        return {"status": "success", "document_id": doc.id}

    except Exception as e:
        db.rollback()

        # 🔥 Log full traceback
        traceback.print_exc()

        # Optional: update document status = FAILED
        # update_doc_status(db, doc_id, "FAILED", str(e))

        raise e

    finally:
        db.close()