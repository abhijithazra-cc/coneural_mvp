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
def _get_doc_by_id(db,org_id,doc_id):
     
     docs=db.query(OrgDocument).filter(OrgDocument.org_id==org_id,OrgDocument.id==doc_id)
     for u in docs:
          print("type u",type(u.file_bytes))
          return u.file_bytes 


@celery_app.task
def heavy_function(x):
    import time
    time.sleep(4)
    return x * 2


@celery_app.task
def filter_sources_by_citation(citations,org_id, sources):
    # 1. Extract all filenames mentioned after "citation"
    # Example fragment: "citation1: virat kohli 4.pdf"
    # cited_files = re.findall(r"([\w\s\-()]+\.(?:pdf|PDF))", response_text)

    # Normalize filenames
    db = SessionLocal()
    # current_user = get_current_active_user()
    cited_files = [f.strip() for f in citations]
    print(cited_files)
    result = {}

    # 2. Filter sources matching the cited filenames
    for src in sources:
        # print(src.metadata['filename'].lower())
        
        filename = src['metadata'].get('filename')


        if filename in cited_files:
            doc_id = src['metadata']["doc_id"]
            page_content = src['page_content']
            print("doc_id",doc_id)
            if doc_id not in result:
                 result[doc_id] = {
                    "filename": filename,
                    "chunks": [],
                    "link":None
                }

            # Append page content to dict
            result[doc_id]["chunks"].append(page_content)
    # print(result)

    output=[]
    for doc_id,items in result.items():
            
            my_doc_bytes=_get_doc_by_id(db=db,org_id=org_id,doc_id=doc_id)
            # docs=_get_doc_by_id(db,current_user,doc_id)
            # full_doc=""
            # for doc in docs:
            #      print("doc",doc)
                 
            #      full_doc+=doc
            #full_doc=''.join(docs.page_content)
            # print("my docs",docs)
            # my_bytes=text_to_pdf_bytes(full_doc)
            # print(my_bytes)
            # print("my_doc_bytes",my_doc_bytes)
            my_bytes=base64.b64decode(my_doc_bytes)

            obj=HighlightText()
            my_bytes=obj.highlight_text(my_bytes,chunks=items['chunks'])
            # with open('my_pdf.pdf',mode='wb') as f:
            #       f.write(my_bytes)
            # my_bytes=base64.b64encode(my_bytes).decode()
            response=upload_pdf_to_github(file_name=items['filename'],owner="rahulkumarcollectcent",token="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",folder='uploads',repo='pdf-viewer',pdf_bytes=my_bytes)
            # print(response)
            
            result[doc_id]['link']=response['link']
            output.append({"filename":result[doc_id]['filename'],"link":result[doc_id]['link'],"doc_id":doc_id})
            # print(my_bytes)
    # print("result",result)
    return output
