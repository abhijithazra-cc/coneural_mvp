import io
import os
import json
import csv
import subprocess
import tempfile
from pathlib import Path
import fitz


class DocumentConverter:
    """
    Universal Document → PDF converter (Bytes → Bytes)

    Supports:
        - Office files (DOCX, XLSX, PPTX) via LibreOffice
        - Images
        - TXT
        - HTML
        - CSV
        - JSON
        - XML
        - Markdown
    """

    OFFICE_TYPES = [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]
    IMAGE_TYPES = [".jpg", ".jpeg", ".png", ".bmp"]
    TEXT_TYPES = [".txt"]
    HTML_TYPES = [".html", ".htm"]
    CSV_TYPES = [".csv"]
    JSON_TYPES = [".json"]
    XML_TYPES = [".xml"]
    MD_TYPES = [".md"]

    # ===============================
    # Public Method
    # ===============================
    def convert_to_pdf_bytes(
        self, file_bytes: bytes, filename: str, extracted_text: str = None
    ) -> bytes:
        ext = Path(filename).suffix.lower()

        if ext in self.OFFICE_TYPES:
            return self._convert_office(file_bytes, ext)

        elif ext in self.IMAGE_TYPES:
            return self._convert_image(file_bytes, extracted_text=extracted_text)

        elif ext in self.TEXT_TYPES:
            return self._convert_text(file_bytes)

        elif ext in self.HTML_TYPES:
            return self._convert_html(file_bytes)

        elif ext in self.CSV_TYPES:
            return self._convert_csv(file_bytes)

        elif ext in self.JSON_TYPES:
            return self._convert_json(file_bytes)

        elif ext in self.XML_TYPES:
            return self._convert_xml(file_bytes)

        elif ext in self.MD_TYPES:
            return self._convert_markdown(file_bytes)

        else:
            raise ValueError(f"Unsupported file type: {ext}")

    # ===============================
    # Office Conversion (LibreOffice)
    # ===============================
    def _convert_office(self, file_bytes: bytes, suffix: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, f"input{suffix}")
            output_path = os.path.join(tmpdir, "input.pdf")

            with open(input_path, "wb") as f:
                f.write(file_bytes)

            subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--nologo",
                    "--nodefault",
                    "--nofirststartwizard",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmpdir,
                    input_path,
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            with open(output_path, "rb") as f:
                return f.read()

    # ===============================
    # Image → PDF
    # ===============================
    # def _convert_image(self, file_bytes: bytes) -> bytes:
    #     from PIL import Image

    #     image = Image.open(io.BytesIO(file_bytes))
    #     pdf_buffer = io.BytesIO()
    #     image.convert("RGB").save(pdf_buffer, format="PDF")
    #     return pdf_buffer.getvalue()
    # PyMuPDF

    def _convert_image(self, file_bytes: bytes, extracted_text: str = None) -> bytes:
        return self._convert_plain_text(extracted_text)

    # ===============================
    # TXT → PDF
    # ===============================
    def _convert_text(self, file_bytes: bytes) -> bytes:
        return self._convert_plain_text(file_bytes.decode("utf-8"))

    # ===============================
    # CSV → PDF
    # ===============================
    def _convert_csv(self, file_bytes: bytes) -> bytes:
        decoded = file_bytes.decode("utf-8")
        reader = csv.reader(decoded.splitlines())
        content = "\n".join([" | ".join(row) for row in reader])
        return self._convert_plain_text(content)

    # ===============================
    # JSON → PDF
    # ===============================
    def _convert_json(self, file_bytes: bytes) -> bytes:
        parsed = json.loads(file_bytes.decode("utf-8"))
        pretty = json.dumps(parsed, indent=4)
        return self._convert_plain_text(pretty)

    # ===============================
    # XML → PDF
    # ===============================
    def _convert_xml(self, file_bytes: bytes) -> bytes:
        return self._convert_plain_text(file_bytes.decode("utf-8"))

    # ===============================
    # Markdown → PDF
    # ===============================
    def _convert_markdown(self, file_bytes: bytes) -> bytes:
        from weasyprint import HTML
        import markdown

        html = markdown.markdown(file_bytes.decode("utf-8"))
        pdf_buffer = io.BytesIO()
        HTML(string=html).write_pdf(pdf_buffer)
        return pdf_buffer.getvalue()

    # ===============================
    # HTML → PDF
    # ===============================
    def _convert_html(self, file_bytes: bytes) -> bytes:
        from weasyprint import HTML

        pdf_buffer = io.BytesIO()
        HTML(string=file_bytes.decode("utf-8")).write_pdf(pdf_buffer)
        return pdf_buffer.getvalue()

    # ===============================
    # Shared Plain Text Renderer
    # ===============================
    def _convert_plain_text(self, text: str) -> bytes:
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import A4

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        for line in text.splitlines():
            elements.append(Paragraph(line, styles["Normal"]))

        doc.build(elements)
        return buffer.getvalue()
