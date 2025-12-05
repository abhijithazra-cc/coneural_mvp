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
#   def highlight_text(self, pdf_bytes, chunks, verbose: bool = False):
#     """
#     Highlights text in both searchable PDF text and inside images (OCR).
#     - pdf_bytes: bytes of input PDF
#     - chunks: list of strings to highlight (case-insensitive). Can be single words or phrases.
#     - verbose: set True to print debug info (helpful while testing)
#     Returns: modified PDF bytes
#     """
#     import fitz
#     import pytesseract
#     from PIL import Image
#     import io
#     import math

#     def dbg(*args):
#         if verbose:
#             print(*args)

#     doc = fitz.open(stream=pdf_bytes, filetype="pdf")

#     # iterate chunks (keep same structure)
#     for raw_chunk in chunks:
#         if not raw_chunk or not str(raw_chunk).strip():
#             continue
#         chunk = str(raw_chunk).strip()
#         chunk_lower = chunk.lower()
#         dbg("Searching for chunk:", repr(chunk))

#         for page_number, page in enumerate(doc, start=1):
#             dbg(f" Page {page_number} — checking normal text...")
#             # (A) Normal searchable text highlight (unchanged logic)
#             try:
#                 # search_for returns list of rects or quads; quads=True gives quad points
#                 text_instances = page.search_for(chunk, quads=True)
#             except Exception as e:
#                 dbg("  page.search_for threw:", e)
#                 text_instances = []

#             for inst in text_instances:
#                 try:
#                     # inst might be rect or quads: add_highlight_annot accepts both
#                     highlight = page.add_highlight_annot(inst)
#                     highlight.update()
#                     dbg("   -> highlighted searchable text on page", page_number)
#                 except Exception as e:
#                     dbg("   -> failed to add highlight for searchable text:", e)

#             # (B) Image OCR search & highlight
#             dbg(f" Page {page_number} — checking images for chunk...")
#             try:
#                 images = page.get_images(full=True)
#             except Exception as e:
#                 dbg("  page.get_images failed:", e)
#                 images = []

#             if not images:
#                 dbg("  -> no images on this page")
#                 continue

#             for img_index, img_info in enumerate(images):
#                 try:
#                     xref = img_info[0]  # image xref
#                 except Exception:
#                     dbg("  -> unexpected img_info format:", img_info)
#                     continue

#                 # extract image bytes
#                 try:
#                     base_image = doc.extract_image(xref)
#                     img_bytes = base_image["image"]
#                 except Exception as e:
#                     dbg("  -> failed to extract image bytes for xref", xref, "err:", e)
#                     continue

#                 # get image bbox on page: use xref (not img_info)
#                 try:
#                     bbox = page.get_image_bbox(xref)
#                 except Exception as e:
#                     # fallback: try passing img_info tuple (older/newer PyMuPDF differences)
#                     try:
#                         bbox = page.get_image_bbox(img_info)
#                     except Exception as e2:
#                         dbg("  -> cannot get image bbox for xref", xref, "errs:", e, e2)
#                         continue

#                 x0, y0, x1, y1 = bbox
#                 w_pdf = x1 - x0
#                 h_pdf = y1 - y0

#                 # load PIL image for OCR
#                 try:
#                     pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
#                 except Exception as e:
#                     dbg("  -> PIL failed to open image for xref", xref, "err:", e)
#                     continue

#                 w_img, h_img = pil_img.size
#                 if w_img == 0 or h_img == 0 or w_pdf == 0 or h_pdf == 0:
#                     dbg("  -> zero-dimension image or pdf-bbox, skipping", w_img, h_img, w_pdf, h_pdf)
#                     continue

#                 # OCR: get word-level boxes
#                 # You can tune config: e.g., lang='eng', psm=6
#                 try:
#                     ocr_data = pytesseract.image_to_data(pil_img, output_type="dict")
#                 except Exception as e:
#                     dbg("  -> pytesseract failed:", e)
#                     continue

#                 # Build a list of word entries with positions
#                 words = []
#                 n_boxes = len(ocr_data.get("text", []))
#                 for i in range(n_boxes):
#                     word_text = str(ocr_data["text"][i]).strip()
#                     if not word_text:
#                         continue
#                     left = int(ocr_data.get("left", [0])[i])
#                     top = int(ocr_data.get("top", [0])[i])
#                     width = int(ocr_data.get("width", [0])[i])
#                     height = int(ocr_data.get("height", [0])[i])
#                     conf = float(ocr_data.get("conf", [-1])[i])
#                     words.append({
#                         "text": word_text,
#                         "text_lower": word_text.lower(),
#                         "left": left,
#                         "top": top,
#                         "w": width,
#                         "h": height,
#                         "conf": conf
#                     })

#                 if not words:
#                     dbg("  -> OCR found no words in image", img_index)
#                     continue

#                 # Prepare for phrase matching: sliding window over words
#                 # Create an array of lowercase texts
#                 word_texts = [w["text_lower"] for w in words]

#                 # Split chunk into tokens (by whitespace) — match contiguous words
#                 chunk_tokens = chunk_lower.split()
#                 m = len(chunk_tokens)
#                 if m == 0:
#                     continue

#                 found_any = False
#                 # sliding window
#                 for start in range(0, len(word_texts) - m + 1):
#                     window = word_texts[start:start + m]
#                     if window == chunk_tokens:
#                         # matched phrase; build bounding rect covering all words in window
#                         sel_words = words[start:start + m]
#                         lefts = [w["left"] for w in sel_words]
#                         tops = [w["top"] for w in sel_words]
#                         rights = [w["left"] + w["w"] for w in sel_words]
#                         bottoms = [w["top"] + w["h"] for w in sel_words]

#                         img_left = min(lefts)
#                         img_top = min(tops)
#                         img_right = max(rights)
#                         img_bottom = max(bottoms)

#                         # map image coordinates -> PDF coordinates
#                         scale_x = float(w_pdf) / float(w_img)
#                         scale_y = float(h_pdf) / float(h_img)

#                         # In many PDFs/PyMuPDF the image bbox (x0,y0) corresponds to top-left of image
#                         # PIL coords also have origin top-left. So mapping is straightforward:
#                         pdf_x0 = x0 + img_left * scale_x
#                         pdf_y0 = y0 + img_top * scale_y
#                         pdf_x1 = x0 + img_right * scale_x
#                         pdf_y1 = y0 + img_bottom * scale_y

#                         # Construct a rect
#                         rect = fitz.Rect(pdf_x0, pdf_y0, pdf_x1, pdf_y1)

#                         try:
#                             # add highlight — add_highlight_annot accepts rect or quad; 
#                             # if it fails, we fallback to rectangle annotation
#                             annot = page.add_highlight_annot(rect)
#                             annot.update()
#                             dbg(f"   -> highlighted phrase in image on page {page_number}, img {img_index}, words {start}-{start+m-1}")
#                         except Exception as e:
#                             dbg("   -> add_highlight_annot failed, trying rect annotation:", e)
#                             try:
#                                 rect_annot = page.add_rect_annot(rect)
#                                 rect_annot.set_colors(stroke=(1, 1, 0))  # not all versions support set_colors
#                                 rect_annot.set_opacity(0.5)
#                                 rect_annot.update()
#                                 dbg("    -> used rect annot as fallback")
#                             except Exception as e2:
#                                 dbg("    -> rect fallback also failed:", e2)

#                         found_any = True

#                 if not found_any:
#                     dbg(f"  -> no phrase match for chunk in image {img_index} on page {page_number}")

#     # write output bytes
#     try:
#         output_bytes = doc.write()
#     except Exception as e:
#         dbg("doc.write() failed, attempting doc.save to bytes:", e)
#         # fallback: save to temp buffer
#         import tempfile
#         tmpname = None
#         try:
#             tf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
#             tmpname = tf.name
#             doc.save(tmpname, garbage=4, deflate=True)
#             tf.close()
#             with open(tmpname, "rb") as f:
#                 output_bytes = f.read()
#         finally:
#             try:
#                 if tmpname:
#                     import os
#                     os.unlink(tmpname)
#             except Exception:
#                 pass

#     doc.close()
#     return output_bytes
