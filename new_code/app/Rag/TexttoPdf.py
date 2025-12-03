from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO

def text_to_pdf_bytes(text: str) -> bytes:
    buffer = BytesIO()

    # Create PDF
    pdf = canvas.Canvas(buffer, pagesize=letter)

    # Starting position
    x, y = 50, 750

    for line in text.split("\n"):
        pdf.drawString(x, y, line)
        y -= 15  # line spacing

        # If page overflow, create new page
        if y < 50:
            pdf.showPage()
            y = 750

    pdf.save()

    # Get the PDF bytes
    buffer.seek(0)
    return buffer.read()

                                        