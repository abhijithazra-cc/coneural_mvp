
# from app.Rag.abstractions.Idocloader import Idocloader

# from io import BytesIO
# from langchain_core.documents import Document

# import docx
# from io import BytesIO
# class DocLoader(Idocloader):
#      def __init__(self):
#           self.documents=None

#      def load_document(self,file:str | bytes,filename:str,id=None):
                
#                 if type(file)==str:
#                     print("file type","str")
#                     docs=[]

#                     doc = docx.Document(BytesIO(file))
#                     for i,p in enumerate(doc):
#                         docs.append(Document(page_content=p.get_text("text"),metadata={"pages":i+1,"filename":filename}))

#                     self.documents=docs
#                 else:
#                     print("file type","bytes")
#                     docs=[]
#                     doc = docx.Document(file)
#                     for i,p in enumerate(doc):
#                         docs.append(Document(page_content=p.get_text("text"),id=id,metadata={"pages":i+1,"filename":filename}))

#                     self.documents=docs
#                     print("my docs",docs)

#      def get_document(self):
#           return self.documents
#      def get_full_content(self):
#           res=""
#           for item in self.documents:
#               res+=" "+item.page_content

#           return res







from app.Rag.abstractions.Idocloader import Idocloader

from io import BytesIO
from langchain_core.documents import Document
import docx


class DocLoader(Idocloader):
     def __init__(self):
          self.documents=None

     def load_document(self, file: str | bytes, filename: str, id=None):

                docs = []

                #  Case 1: file is a PATH (string)
                if isinstance(file, str):
                    print("file type", "str")
                    
                    doc = docx.Document(file)

                #  Case 2: file is BYTES
                else:
                    print("file type", "bytes")
                    
                    bio = BytesIO(file)
                    bio.seek(0)
                    doc = docx.Document(bio)

                #  Extract paragraphs safely (python-docx Document is NOT iterable like you used)
                for i, p in enumerate(doc.paragraphs):
                    text = (p.text or "").strip()
                    if not text:
                        continue

                    # keep your id behavior (you had id only in bytes branch)
                    if isinstance(file, str):
                        docs.append(
                            Document(
                                page_content=text,
                                metadata={"pages": i + 1, "filename": filename},
                            )
                        )
                    else:
                        docs.append(
                            Document(
                                page_content=text,
                                id=id,
                                metadata={"pages": i + 1, "filename": filename},
                            )
                        )

                self.documents = docs
                print("my docs", docs)

     def get_document(self):
          return self.documents

     def get_full_content(self):
          res = ""
          for item in self.documents:
              res += " " + item.page_content
          return res
