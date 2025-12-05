import fitz  # PyMuPDF

from langchain_core.documents import Document
class HighlightText ():
    def __init__(self,pdf_bytes=None,output_path=""):
        self.pdf_bytes=pdf_bytes
        self.output_path=output_path
    def set_bytes(self,bytes):
        self.pdf_bytes=bytes
    def highlight_text(self,chunks):
        
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        for chunk in chunks:
            for page in doc:
                text_instances = page.search_for(chunk.page_content, quads=True)  # use quads for accurate text regions

                for inst in text_instances:
        # Add highlight annotation
                    highlight = page.add_highlight_annot(inst)
                    highlight.update()

        doc.save(self.output_path, incremental=False)
        doc.close()




# Text/paragraph to highlight
target_text = """The Most Important Things You Can Do about Rapid Climate Change"""



# hi=HighlightText(pdf_path='globalwarming.pdf',output_path='output.pdf')

# hi.highlight_text([Document(page_content=target_text)])

# print("Done! Saved:")
