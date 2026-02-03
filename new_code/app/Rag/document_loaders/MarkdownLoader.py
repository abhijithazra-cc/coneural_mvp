import markdown
from html.parser import HTMLParser
from langchain_core.documents import Document
from app.Rag.abstractions.Idocloader import Idocloader


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        if data.strip():
            self.text.append(data)

    def get_text(self) -> str:
        return "\n".join(self.text)


class MarkdownLoader(Idocloader):
    def __init__(self):
        self.documents = []

    def load_document(self, file: str | bytes, filename: str):
        docs = []

        if isinstance(file, str):
            print("file type: str")
            self.documents = docs
            return docs

        print("Loading markdown document...")
        print("filename:", filename)

        content = self.extract_text_from_markdown_bytes(file)

        docs.append(
            Document(
                page_content=content,
                metadata={
                    "pages": 1,
                    "filename": filename,
                },
            )
        )

        self.documents = docs
        return docs

    def extract_text_from_markdown_bytes(self, md_bytes: bytes) -> str:
        md_text = md_bytes.decode("utf-8", errors="ignore")

        # Markdown → HTML
        html = markdown.markdown(md_text)

        # HTML → plain text
        parser = _HTMLTextExtractor()
        parser.feed(html)

        return parser.get_text().strip()

    def get_document(self):
        return self.documents

    def get_full_content(self):
        return " ".join(doc.page_content for doc in self.documents)
