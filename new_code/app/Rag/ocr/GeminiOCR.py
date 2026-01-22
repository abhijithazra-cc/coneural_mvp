import google.generativeai as genai

from app.Rag.abstractions.IocrProvider import OCRProvider

class GeminiOCR(OCRProvider):

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    def extract(self, image_bytes: bytes) -> str:
        response = self.model.generate_content(
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": "Extract ALL text and data visible in this image."},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": image_bytes
                            }
                        }
                    ]
                }
            ]
        )
        return response.text
