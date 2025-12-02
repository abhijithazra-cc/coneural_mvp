import fitz  # PyMuPDF

from langchain_core.documents import Document
class HighlightText ():

    def highlight_text(self,pdf_bytes,chunks):
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for chunk in chunks:
            for page in doc:
                text_instances = page.search_for(chunk, quads=True)  # use quads for accurate text regions

                for inst in text_instances:
        # Add highlight annotation
                    highlight = page.add_highlight_annot(inst)
                    highlight.update()
        output_bytes=doc.write()
        # doc.save(self.output_path, incremental=False)
        doc.close()
        return output_bytes
