import base64
from openai import OpenAI

from app.Rag.abstractions.IocrProvider import OCRProvider
from langchain_openai import ChatOpenAI
class OpenaiOCR(OCRProvider):

    def __init__(self, api_key: str):
        self.llm = ChatOpenAI(api_key=api_key,model='gpt-4o')

    def extract(self, image_bytes: bytes, filename: str) -> str:
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        type=filename.split('.')[1]
        print("file type",type)
        response=self.llm.invoke(        input=[{
                "role": "user",
                "content": [
            {"type": "text", "text": "Extract all text from this image."},
            {
                "type": "image_url",
                "image_url":{"url": f"data:image/{type};base64,{image_base64}"},
            },
        ]
            }])
        # response = self.client.completions.create(
        #     model="gpt-4.1-mini",
        #     input=[{
        #         "role": "user",
        #         "content": [
        #             {"type": "input_text", "text": "Extract ALL text and data visible in this image."},
        #             {"type": "input_image", "image_base64": image_base64}
        #         ]
        #     }]
        # )

        return response.content
