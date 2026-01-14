import os
from celery import Celery
# app/routers/qa.py

from app.models.doc_models import OrgDocument,DocChunk  

from app.Rag.HighlightText import HighlightText
from app.database import SessionLocal
import base64
from app.Rag.PdfUploader import upload_pdf_to_github
celery_app = Celery(
    "tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)
def _get_doc_by_id(db,org_id,document_id):
     
     docs=db.query(OrgDocument).filter(OrgDocument.org_id==org_id,OrgDocument.id==document_id)
     for u in docs:
          print("type u",type(u.file_bytes))
          return u.file_bytes ,u.title


@celery_app.task
def heavy_function(x):
    import time
    time.sleep(4)
    return x * 2



# @celery_app.task
# def helper_filter_sources_by_citation(cited_files,org_id, src):
    
#         # print(src.metadata['filename'].lower())
#         db = SessionLocal()
#         filename = src['metadata'].get('filename')
#         result = {}

#         if filename in cited_files:
#             document_id = src['metadata']["document_id"]
#             page_content = src['page_content']

#             my_doc_bytes,title=_get_doc_by_id(db=db,org_id=org_id,document_id=document_id)
#             print("doc_id",document_id,"my_doc_bytes type",type(my_doc_bytes))

#             my_bytes=base64.b64decode(my_doc_bytes)

#             obj=HighlightText()
#             my_bytes=obj.highlight_text(my_bytes,chunks=page_content)
#             response=upload_pdf_to_github(file_name=filename,owner="rahulkumarcollectcent",token="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",folder='uploads',repo='pdf-viewer')
#             print(response)
#             return {"filename":title,"link":response['link'],"document_id":document_id}
#         return None
 



# # # @celery_app.task
# # def filter_sources_by_citation(citations,org_id, sources):
# #     # 1. Extract all filenames mentioned after "citation"
# #     # Example fragment: "citation1: virat kohli 4.pdf"
# #     # cited_files = re.findall(r"([\w\s\-()]+\.(?:pdf|PDF))", response_text)

# #     # Normalize filenames
# #     db = SessionLocal()
# #     # current_user = get_current_active_user()
# #     cited_files = [f.strip() for f in citations]
# #     # print(cited_files)
# #     result = {}

# #     # 2. Filter sources matching the cited filenames
# #     for src in sources:
# #         # print(src.metadata['filename'].lower())
        
# #         filename = src['metadata'].get('filename')


# #         if filename in cited_files:
# #             document_id = src['metadata']["document_id"]
# #             page_content = src['page_content']
# #             # print("document_id",document_id)
# #             print("hi")
# #             if document_id not in result:
# #                  result[document_id] = {
# #                     "filename": filename,
# #                     "chunks": [],
# #                     "link":None
# #                 }

# #             # Append page content to dict
# #             result[document_id]["chunks"].append(page_content)
# #     # print(result)

# #     output=[]
# #     for document_id,items in result.items():
            
# #             my_doc_bytes,title=_get_doc_by_id(db=db,org_id=org_id,document_id=document_id)
# #             print("doc_id",document_id,"my_doc_bytes type",type(my_doc_bytes))
# #             # docs=_get_doc_by_id(db,current_user,document_id)
# #             # full_doc=""
# #             # for doc in docs:
# #             #      print("doc",doc)
                 
# #             #      full_doc+=doc
# #             #full_doc=''.join(docs.page_content)
# #             # print("my docs",docs)
# #             # my_bytes=text_to_pdf_bytes(full_doc)
# #             # print(my_bytes)
# #             # print("my_doc_bytes",my_doc_bytes)
# #             my_bytes=base64.b64decode(my_doc_bytes)

# #             obj=HighlightText()
# #             my_bytes=obj.highlight_text(my_bytes,chunks=items['chunks'])
# #             # with open('my_pdf.pdf',mode='wb') as f:
# #             #       f.write(my_bytes)
# #             # my_bytes=base64.b64encode(my_bytes).decode()
# #             response=upload_pdf_to_github(file_name=items['filename'],owner="rahulkumarcollectcent",token="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",folder='uploads',repo='pdf-viewer',pdf_bytes=my_bytes)
# #             # print(response)
            
# #             result[document_id]['link']=response['link']
# #             # print("github token",response['github_token'])
# #             output.append({"filename":title,"link":result[document_id]['link'],"document_id":document_id})
# #             # print(my_bytes)
# #     # print("result",result)
# #     return output



# def filter_sources_by_citation(citations,org_id, sources):

#     # current_user = get_current_active_user()
#     cited_files = [f.strip() for f in citations]
#     # print(cited_files)
#     output = []

#     # 2. Filter sources matching the cited filenames
#     for src in sources:
#         # print(src.metadata['filename'].lower())
        
#         filtered_result = helper_filter_sources_by_citation.delay(cited_files,org_id, src)
#         output.append(filtered_result.id)
#     return output   



def filter_sources_by_citation(citations, org_id, sources):
    # keep only real file citations
    cited_files = {
        c.strip() for c in citations
        
    }

    # filename → {document_id, chunks[]}
    grouped = {}

    for src in sources:
        filename = src.get("metadata", {}).get("filename")
        if filename not in cited_files:
            continue

        document_id = src["metadata"]["document_id"]
        chunk = src["page_content"]

        if filename not in grouped:
            grouped[filename] = {
                "document_id": document_id,
                "chunks": []
            }

        grouped[filename]["chunks"].append(chunk)

    output = []

    for filename, data in grouped.items():
        task = helper_filter_sources_by_citation.delay(
            filename,
            org_id,
            data["document_id"],
            data["chunks"]
        )
        output.append({"filename": filename, "link": f"/qa/pdf/{task.id}"})

    return output
import time

@celery_app.task
def helper_filter_sources_by_citation(filename, org_id, document_id, chunks):
    db = SessionLocal()
    # time.sleep(20)  # Simulate a delay for heavy processing
    my_doc_bytes, title = _get_doc_by_id(
        db=db,
        org_id=org_id,
        document_id=document_id
    )

    my_bytes = base64.b64decode(my_doc_bytes)

    obj = HighlightText()
    my_bytes = obj.highlight_text(my_bytes, chunks=chunks)

    # response = upload_pdf_to_github(
    #     file_name=filename,
    #     owner="rahulkumarcollectcent",
    #     token=os.getenv("GITHUB_TOKEN"),
    #     folder="uploads",
    #     repo="pdf-viewer",
    #     pdf_bytes=my_bytes
    # )

    return {
        "filename": title,
        "pdf": base64.b64encode(my_bytes).decode("utf-8"),
        "document_id": document_id
    }
  
