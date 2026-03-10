import os
from pathlib import Path
from celery import Celery

# # # app/routers/qa.py

from app.models.doc_models import OrgDocument, DocChunk

# celery_app = Celery(
#     "tasks",
#     broker="redis://172.22.94.123:6379/0",
#     backend="redis://172.22.94.123:6379/0",
# )
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
    task_time_limit=300,
    task_soft_time_limit=270,
)
from app.Rag.HighlightText import HighlightText

# from app.database import SessionLocal
# import base64
from app.Rag.PdfUploader import upload_pdf_to_github

# celery_app = Celery(
#     "tasks",
#     broker="redis://localhost:6379/0",
#     backend="redis://localhost:6379/0",
# )
# # # celery_app.autodiscover_tasks(["app.tasks"])


def _get_doc_by_id(db, org_id, document_id):

    docs = db.query(OrgDocument).filter(
        OrgDocument.org_id == org_id, OrgDocument.id == document_id
    )
    for u in docs:
        print("type u", type(u.file_bytes))
        return u.file_bytes, u.title


# # @celery_app.task
# # def heavy_function(x):
# #     import time
# #     time.sleep(80)
# #     return x * 2


# # # @celery_app.task
# # # def helper_filter_sources_by_citation(cited_files,org_id, src):

# # #         # print(src.metadata['filename'].lower())
# # #         db = SessionLocal()
# # #         filename = src['metadata'].get('filename')
# # #         result = {}

# # #         if filename in cited_files:
# # #             document_id = src['metadata']["document_id"]
# # #             page_content = src['page_content']

# # #             my_doc_bytes,title=_get_doc_by_id(db=db,org_id=org_id,document_id=document_id)
# # #             print("doc_id",document_id,"my_doc_bytes type",type(my_doc_bytes))

# # #             my_bytes=base64.b64decode(my_doc_bytes)

# # #             obj=HighlightText()
# # #             my_bytes=obj.highlight_text(my_bytes,chunks=page_content)
# # #             response=upload_pdf_to_github(file_name=filename,owner="rahulkumarcollectcent",token="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",folder='uploads',repo='pdf-viewer')
# # #             print(response)
# # #             return {"filename":title,"link":response['link'],"document_id":document_id}
# # #         return None


# @celery_app.task
# def filter_sources_by_citation(citations,org_id, sources):
#     # 1. Extract all filenames mentioned after "citation"
#     # Example fragment: "citation1: virat kohli 4.pdf"
#     # cited_files = re.findall(r"([\w\s\-()]+\.(?:pdf|PDF))", response_text)

#     # Normalize filenames
#     db = SessionLocal()
#     # current_user = get_current_active_user()
#     cited_files = [f.strip() for f in citations]
#     # print(cited_files)
#     result = {}

#     # 2. Filter sources matching the cited filenames
#     for src in sources:
#         # print(src.metadata['filename'].lower())

#         filename = src['metadata'].get('filename')


#         if filename in cited_files:
#             document_id = src['metadata']["document_id"]
#             page_content = src['page_content']
#             # print("document_id",document_id)
#             print("hi")
#             if document_id not in result:
#                  result[document_id] = {
#                     "filename": filename,
#                     "chunks": [],
#                     "link":None
#                 }

#             # Append page content to dict
#             result[document_id]["chunks"].append(page_content)
#     # print(result)

#     output=[]
#     for document_id,items in result.items():

#             my_doc_bytes,title=_get_doc_by_id(db=db,org_id=org_id,document_id=document_id)
#             print("doc_id",document_id,"my_doc_bytes type",type(my_doc_bytes))
#             # docs=_get_doc_by_id(db,current_user,document_id)
#             # full_doc=""
#             # for doc in docs:
#             #      print("doc",doc)

#             #      full_doc+=doc
#             #full_doc=''.join(docs.page_content)
#             # print("my docs",docs)
#             # my_bytes=text_to_pdf_bytes(full_doc)
#             # print(my_bytes)
#             # print("my_doc_bytes",my_doc_bytes)
#             my_bytes=base64.b64decode(my_doc_bytes)

#             obj=HighlightText()
#             my_bytes=obj.highlight_text(my_bytes,chunks=items['chunks'])
#             # with open('my_pdf.pdf',mode='wb') as f:
#             #       f.write(my_bytes)
#             # my_bytes=base64.b64encode(my_bytes).decode()
#             response=upload_pdf_to_github(file_name=items['filename'],owner="rahulkumarcollectcent",token="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",folder='uploads',repo='pdf-viewer',pdf_bytes=my_bytes)
#             # print(response)

#             result[document_id]['link']=response['link']
#             # print("github token",response['github_token'])
#             output.append({"filename":title,"link":result[document_id]['link'],"document_id":document_id})
#             # print(my_bytes)
#     # print("result",result)
#     return output


# # # def filter_sources_by_citation(citations,org_id, sources):

# # #     # current_user = get_current_active_user()
# # #     cited_files = [f.strip() for f in citations]
# # #     # print(cited_files)
# # #     output = []

# # #     # 2. Filter sources matching the cited filenames
# # #     for src in sources:
# # #         # print(src.metadata['filename'].lower())

# # #         filtered_result = helper_filter_sources_by_citation.delay(cited_files,org_id, src)
# # #         output.append(filtered_result.id)
# # #     return output


def filter_sources_by_citation(citations, org_id, sources):
    # keep only real file citations
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


# import time
# from app.Rag.CompareDoc import CompareDoc
# from app.services.document import _ensure_org_admin,_ensure_org_admin_or_dept_admin_or_author,_ensure_can_manage_global_docs,_ensure_can_manage_dept_docs,_ensure_same_org,_check_duplicate
# from app.database import SessionLocal
# import base64, pickle, time, traceback
# from sqlalchemy.orm import Session
# from app.Rag.VectorManager import vectorManager
# from app.services.auth import get_current_active_user
# from app.utils.chunking import extract_text_from_file, chunk_text
# # from app.Rag.text_splitters.CharacterSplitter import CharacterSplitter
# from app.utils.embeddings import embed_texts
# from app.Rag.utils import embeddings,BASE_DIR
# MAX_FILE_BYTES = 5 * 1024 * 1024
# from app.services.embedding_token import user_license_and_token_update,_count_tokens_for_openai_embeddings,dept_license_and_token_update,user_license_and_token_update,org_license_and_token_update
# from app.utils.faiss_manager import add_vectors
# from app.utils.text_extractors import extract_text

# # @celery_app.task
# # def upload_file_to_db_task(

# #     payload: None,
# #     original_filename: str,
# #     content_type: str,
# #     org_id: int,
# #     dept_id: int | None,
# #     user_id: int,
# #     tag: str,
# #     doc_scope: str,
# # ):
# #     db: Session = SessionLocal()

# #     try:
# #         # 1) Read file


# #         if not payload:
# #             raise ValueError("Empty file")

# #         if len(payload) > MAX_FILE_BYTES:
# #             raise ValueError("File too large")

# #         # 2) Extract text
# #         filename = f"{org_id}_{user_id}_{int(time.time())}_{original_filename}"

# #         text, docs = extract_text(
# #             payload,
# #             filename=filename,
# #             mimetype=content_type or "",
# #         )

# #         new_text = text.lower()

# #         duplicate = _check_duplicate(
# #             db=db,
# #             org_id=org_id,
# #             dept_id=dept_id,
# #             new_text=new_text,
# #             threshold=0.8,
# #         )

# #         # 3) Minhash
# #         compdoc = CompareDoc()
# #         m = compdoc.create_minhash(text)
# #         doc_hash = pickle.dumps(m)

# #         # 4) Chunking
# #         chunks = chunk_text(docs=docs, max_tokens=512, overlap=120)
# #         if not chunks:
# #             raise ValueError("No chunks extracted")

# #         # 5) Store document
# #         doc_bytes = base64.b64encode(payload)

# #         doc = OrgDocument(
# #             org_id=org_id,
# #             dept_id=None if doc_scope == "global" else dept_id,
# #             uploaded_by=user_id,
# #             title=original_filename,
# #             tag=tag,
# #             scope=doc_scope,
# #             filename=filename,
# #             mime_type=content_type or "application/octet-stream",
# #             size_bytes=len(payload),
# #             file_bytes=doc_bytes,
# #             hash_bytes=doc_hash,
# #         )

# #         db.add(doc)
# #         db.flush()  # get doc.id
# #         print("abjijeet")
# #         # 6) Vector store
# #         vs = vectorManager.get_store(
# #             embeddings=embeddings,
# #             persist_dir=f"{BASE_DIR}/{org_id}",
# #         )

# #         vs.add_documents(
# #             documents=chunks,
# #             document_id=doc.id,
# #             dept_id=dept_id if doc_scope == "department" else "global",
# #         )
# #         print("sachin chaudhary")
# #         # 7) Token accounting
# #         token = sum(
# #             _count_tokens_for_openai_embeddings(
# #                 model_name="text-embedding-ada-002",
# #                 texts=[chunk.page_content],
# #             )
# #             for chunk in chunks
# #         )

# #         if dept_id and doc_scope == "department":
# #             user_license_and_token_update(db, user_id, dept_id, token)
# #             dept_license_and_token_update(db, dept_id, org_id, token)
# #         else:
# #             org_license_and_token_update(db, org_id, token)

# #         # 8) Save chunks
# #         db.add_all(
# #             [
# #                 DocChunk(document_id=doc.id, content=chunk.page_content)
# #                 for chunk in chunks
# #             ]
# #         )

# #         db.commit()
# #         return {"status": "success", "document_id": doc.id}

# #     except Exception as e:
# #         db.rollback()

# #         # 🔥 Log full traceback
# #         traceback.print_exc()

# #         # Optional: update document status = FAILED
# #         # update_doc_status(db, doc_id, "FAILED", str(e))

# #         raise e

# #     finally:
# #         db.close()


@celery_app.task
def helper_filter_sources_by_citation(filename, org_id, document_id, chunks):
    db = SessionLocal()
    # time.sleep(20)  # Simulate a delay for heavy processing
    my_doc_bytes, title = _get_doc_by_id(db=db, org_id=org_id, document_id=document_id)

    my_bytes = base64.b64decode(my_doc_bytes)

    obj = HighlightText()
    my_bytes = obj.highlight_text(my_bytes, chunks=chunks)

    # response = upload_pdf_to_github(
    #     file_name=filename,
    #     owner="rahulkumarcollectcent",
    #     token=os.getenv("GITHUB_TOKEN"),
    #     folder="uploads",
    #     repo="pdf-viewer",
    #     pdf_bytes=my_bytes,
    # )
    # print(response)

    return {
        "filename": title,
        "pdf": base64.b64encode(my_bytes).decode("utf-8"),
        "document_id": document_id,
        "link": "link_placeholder",
    }


# import time
# import base64
# import pickle
# import traceback
# from celery import Celery, chain
# from sqlalchemy.orm import Session

# # =========================
# # Celery App
# # =========================

# celery_app = Celery(
#     "tasks",
#     broker="redis://localhost:6379/0",
#     backend="redis://localhost:6379/0",
# )

# celery_app.conf.update(
#     task_serializer="json",
#     accept_content=["json"],
#     # result_serializer="json"

#     task_acks_late=True,
#     worker_prefetch_multiplier=1,

#     task_time_limit=300,
#     task_soft_time_limit=270,
# )

# # =========================
# # Imports (local app)
# # =========================

# from app.database import SessionLocal
# from app.models.doc_models import OrgDocument, DocChunk
# from app.utils.text_extractors import extract_text
# from app.utils.chunking import chunk_text
# from app.Rag.CompareDoc import CompareDoc
# from app.Rag.VectorManager import vectorManager
# from app.Rag.utils import BASE_DIR
# from app.Rag.utils import embeddings
# from app.services.document import _check_duplicate
# from app.services.embedding_token import (
#     _count_tokens_for_openai_embeddings,
#     user_license_and_token_update,
#     dept_license_and_token_update,
#     org_license_and_token_update,
# )

# MAX_FILE_BYTES = 5 * 1024 * 1024

# # =========================
# # TASK 1: Extract + Store
# # =========================

# @celery_app.task(

#     autoretry_for=(Exception,),
#     retry_backoff=10,
#     retry_kwargs={"max_retries": 3},
# )
# def extract_and_store_doc_task(

#     payload: bytes,
#     original_filename: str,
#     content_type: str,
#     org_id: int,
#     dept_id: int | None,
#     user_id: int,
#     tag: str,
#     doc_scope: str,
# ):
#     db: Session = SessionLocal()
#     try:
#         if not payload or len(payload) > MAX_FILE_BYTES:
#             raise ValueError("Invalid file")

#         filename = f"{org_id}_{user_id}_{int(time.time())}_{original_filename}"

#         text, docs = extract_text(
#             payload,
#             filename=filename,
#             mimetype=content_type or "",
#         )

#         _check_duplicate(
#             db=db,
#             org_id=org_id,
#             dept_id=dept_id,
#             new_text=text.lower(),
#             threshold=0.8,
#         )

#         compdoc = CompareDoc()
#         doc_hash = pickle.dumps(compdoc.create_minhash(text))

#         doc = OrgDocument(
#             org_id=org_id,
#             dept_id=None if doc_scope == "global" else dept_id,
#             uploaded_by=user_id,
#             title=original_filename,
#             tag=tag,
#             scope=doc_scope,
#             filename=filename,
#             mime_type=content_type or "application/octet-stream",
#             size_bytes=len(payload),
#             file_bytes=base64.b64encode(payload),
#             hash_bytes=doc_hash,
#         )

#         db.add(doc)
#         db.commit()
#         db.refresh(doc)

#         return {
#             "doc_id": doc.id,
#             "docs": docs,
#             "org_id": org_id,
#             "dept_id": dept_id,
#             "scope": doc_scope,
#         }

#     except Exception:
#         db.rollback()
#         traceback.print_exc()
#         raise
#     finally:
#         db.close()

# # =========================
# # TASK 2: Chunk + Save
# # =========================

# @celery_app.task
# def chunk_and_store_task( payload: dict):
#     db: Session = SessionLocal()
#     try:
#         chunks = chunk_text(
#             docs=payload["docs"],
#             max_tokens=512,
#             overlap=120,
#         )

#         if not chunks:
#             raise ValueError("No chunks extracted")

#         db.add_all(
#             [
#                 DocChunk(
#                     document_id=payload["doc_id"],
#                     content=chunk.page_content,
#                 )
#                 for chunk in chunks
#             ]
#         )
#         db.commit()

#         return {
#             "doc_id": payload["doc_id"],
#             # "chunks": [c.page_content for c in chunks],
#             "org_id": payload["org_id"],
#             "dept_id": payload["dept_id"],
#             "scope": payload["scope"],
#         }

#     finally:
#         db.close()

# # =========================
# # TASK 3: Embed + FAISS
# # =========================

# @celery_app.task( time_limit=180)
# def embed_and_index_task( payload: dict):
#     db: Session = SessionLocal()
#     try:
#         vs = vectorManager.get_store(
#             embeddings=embeddings,
#             persist_dir=f"{BASE_DIR}/{payload['org_id']}",
#         )

#         vs.add_texts(
#             texts=payload["chunks"],
#             document_id=payload["doc_id"],
#             dept_id=payload["dept_id"] if payload["scope"] == "department" else "global",
#         )

#         token_count = sum(
#             _count_tokens_for_openai_embeddings(
#                 model_name="text-embedding-ada-002",
#                 texts=[text],
#             )
#             for text in payload["chunks"]
#         )

#         if payload["dept_id"] and payload["scope"] == "department":
#             user_license_and_token_update(db, payload["doc_id"], payload["dept_id"], token_count)
#             dept_license_and_token_update(db, payload["dept_id"], payload["org_id"], token_count)
#         else:
#             org_license_and_token_update(db, payload["org_id"], token_count)

#         db.commit()
#         return {"status": "success", "doc_id": payload["doc_id"]}

#     finally:
#         db.close()

# # =========================
# # PIPELINE (ENTRY POINT)
# # =========================
# @celery_app.task
# def upload_file_to_db_task(
#     payload: bytes,
#     original_filename: str,
#     content_type: str,
#     org_id: int,
#     dept_id: int | None,
#     user_id: int,
#     tag: str,
#     doc_scope: str,
# ):
#     return chain(
#         extract_and_store_doc_task.s(
#             payload,
#             original_filename,
#             content_type,
#             org_id,
#             dept_id,
#             user_id,
#             tag,
#             doc_scope,
#         ),
#         chunk_and_store_task.s(),
#         embed_and_index_task.s(),
#     ).apply_async()


import time
import base64
import pickle
import traceback
from celery import Celery, chain
from sqlalchemy.orm import Session


from app.database import SessionLocal
from app.models.doc_models import OrgDocument, DocChunk
from app.utils.text_extractors import extract_text
from app.utils.chunking import chunk_text
from app.Rag.CompareDoc import CompareDoc
from app.Rag.VectorManager import vectorManager
from app.Rag.utils import BASE_DIR, embeddings
from app.services.document import _check_duplicate
from app.services.embedding_token import (
    _count_tokens_for_openai_embeddings,
    user_license_and_token_update,
    dept_license_and_token_update,
    org_license_and_token_update,
)

from langchain_core.documents import Document


MAX_FILE_BYTES = 5 * 1024 * 1024

# =========================
# TASK 1: Extract + Store
# =========================
from app.Rag.DocumentConverter import DocumentConverter
from pathlib import Path


@celery_app.task(
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_kwargs={"max_retries": 3},
)
def extract_and_store_doc_task(
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
    db: Session = SessionLocal()
    try:
        if not payload:
            raise ValueError("Empty file")

        if len(payload) > MAX_FILE_BYTES:
            raise ValueError("File too large")

        text, docs = extract_text(
            payload,
            filename=filename,
            mimetype=content_type or "",
        )

        _check_duplicate(
            db=db,
            org_id=org_id,
            dept_id=dept_id,
            new_text=text.lower(),
            threshold=0.8,
        )
        doc_converter = DocumentConverter()
        # filename_without_ext = Path(original_filename).stem
        file_ext = Path(original_filename).suffix
        if file_ext != ".pdf":
            payload = doc_converter.convert_to_pdf_bytes(
                file_bytes=payload, filename=original_filename, extracted_text=text
            )
        compdoc = CompareDoc()
        doc_hash = pickle.dumps(compdoc.create_minhash(text))

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
            file_bytes=base64.b64encode(payload),
            hash_bytes=doc_hash,
        )

        db.add(doc)
        db.commit()
        db.refresh(doc)

        # ✅ Convert LangChain Document → dict (JSON safe)
        serializable_docs = [
            {
                "page_content": d.page_content,
                "metadata": d.metadata,
            }
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

    except Exception:
        db.rollback()
        traceback.print_exc()
        raise
    finally:
        db.close()


# =========================
# TASK 2: Chunk + Store
# =========================


@celery_app.task
def chunk_and_store_task(payload: dict):
    db: Session = SessionLocal()
    try:
        # ✅ Rebuild LangChain Document objects
        docs = [
            Document(
                page_content=d["page_content"],
                metadata=d["metadata"],
            )
            for d in payload["docs"]
        ]
        # text=" ".join([doc.page_content for doc in docs])
        chunks = chunk_text(
            docs=docs,
            max_tokens=512,
            overlap=120,
        )

        if not chunks:
            raise ValueError("No chunks extracted")

        db.add_all(
            [
                DocChunk(
                    document_id=payload["doc_id"],
                    content=chunk.page_content,
                )
                for chunk in chunks
            ]
        )
        db.commit()

        return {
            "doc_id": payload["doc_id"],
            "chunks": [
                {"page_content": c.page_content, "metadata": c.metadata} for c in chunks
            ],  # ✅ strings only
            "user_id": payload["user_id"],
            "org_id": payload["org_id"],
            "dept_id": payload["dept_id"],
            "scope": payload["scope"],
        }

    finally:
        db.close()


# =========================
# TASK 3: Embed + FAISS
# =========================


@celery_app.task(time_limit=180)
def embed_and_index_task(payload: dict):
    db: Session = SessionLocal()
    try:
        vs = vectorManager.get_store(
            embeddings=embeddings,
            persist_dir=f"{BASE_DIR}/{payload['org_id']}",
        )
        print("payload in embed_and_index_task", payload)
        documents = [
            Document(page_content=chunk["page_content"], metadata=chunk["metadata"])
            for chunk in payload["chunks"]
        ]
        # print("dept_id",payload["dept_id"],"scope",payload["scope"])
        if payload["scope"] == "department":
            dept_id = payload["dept_id"]
        else:
            dept_id = "global"

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
        user_license_and_token_update(
            db,
            payload["user_id"],
            token_count,
        )
        org_license_and_token_update(
            db,
            payload["org_id"],
            token_count,
        )
        # if payload["dept_id"] and payload["scope"] == "department":
        #     user_license_and_token_update(
        #         db,
        #         payload["user_id"],
        #         payload["dept_id"],
        #         token_count,
        #     )
        #     # user_license_and_token_update(
        #     #     db,
        #     #     payload["doc_id"],
        #     #     payload["dept_id"],
        #     #     token_count,
        #     # )
        #     dept_license_and_token_update(
        #         db,
        #         payload["dept_id"],
        #         payload["org_id"],
        #         token_count,
        #     )
        # else:
        #     org_license_and_token_update(
        #         db,
        #         payload["org_id"],
        #         token_count,
        #     )

        db.commit()
        return {"status": "success", "doc_id": payload["doc_id"]}

    finally:
        db.close()


# =========================
# PIPELINE ENTRY POINT
# =========================


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
