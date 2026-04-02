# from app.Rag.abstractions.Idocloader import Idocloader

# from io import BytesIO
# from langchain_core.documents import Document

# import pandas as pd


# class ExcelLoader(Idocloader):
#     def __init__(self):
#         self.documents = None

#     def load_document(self, file: str | bytes, filename: str, id=None):

#         if type(file) == str:
#             print("file type", "str")
#             docs = []

#             # str treated as a file path for Excel
#             xls = pd.ExcelFile(file)
#             for sheet_name in xls.sheet_names:
#                 df = xls.parse(sheet_name)
#                 for i, row in enumerate(df.itertuples(index=False)):
#                     row_text = ", ".join(
#                         f"{col}: {val}"
#                         for col, val in zip(df.columns, row)
#                     )
#                     docs.append(
#                         Document(
#                             page_content=row_text,
#                             metadata={
#                                 "row": i + 1,
#                                 "sheet": sheet_name,
#                                 "filename": filename,
#                             },
#                         )
#                     )

#             self.documents = docs

#         else:
#             print("file type", "bytes")
#             docs = []

#             xls = pd.ExcelFile(BytesIO(file))
#             for sheet_name in xls.sheet_names:
#                 df = xls.parse(sheet_name)
#                 for i, row in enumerate(df.itertuples(index=False)):
#                     row_text = ", ".join(
#                         f"{col}: {val}"
#                         for col, val in zip(df.columns, row)
#                     )
#                     docs.append(
#                         Document(
#                             page_content=row_text,
#                             id=id,
#                             metadata={
#                                 "row": i + 1,
#                                 "sheet": sheet_name,
#                                 "filename": filename,
#                             },
#                         )
#                     )

#             self.documents = docs
#             print("my docs", docs)

#     def get_document(self):
#         return self.documents

#     def get_full_content(self):
#         res = ""
#         for item in self.documents:
#             res += " " + item.page_content

#         return res






import pandas as pd
from io import BytesIO
from langchain_core.documents import Document
from app.Rag.abstractions.Idocloader import Idocloader


class ExcelLoader(Idocloader):
    def __init__(self):
        self.documents = None

    def _parse_xls(self, xls: pd.ExcelFile, filename: str, id=None):
        docs = []
        for sheet_name in xls.sheet_names:
            # Try to find the real header row by scanning for the first
            # row that has mostly non-null, non-"Unnamed" values
            raw_df = xls.parse(sheet_name, header=None)
            header_row = self._detect_header_row(raw_df)

            df = xls.parse(sheet_name, skiprows=header_row)

            # Rename any still-unnamed columns using positional fallback
            df.columns = [
                col if not str(col).startswith("Unnamed") else f"Col_{i}"
                for i, col in enumerate(df.columns)
            ]

            # Drop fully empty rows
            df.dropna(how="all", inplace=True)

            # Build a sheet-level preamble so the LLM knows what sheet it's reading
            preamble = f"Sheet: {sheet_name} | File: {filename}"

            for i, row in df.iterrows():
                row_text = preamble + " | " + ", ".join(
                    f"{col}: {val}"
                    for col, val in row.items()
                    if pd.notna(val)           # skip NaN cells entirely
                )
                docs.append(
                    Document(
                        page_content=row_text,
                        id=id,
                        metadata={
                            "row": i + 1,
                            "sheet": sheet_name,
                            "filename": filename,
                        },
                    )
                )
        return docs

    def _detect_header_row(self, raw_df: pd.DataFrame) -> int:
        """Return the index of the first row that looks like a real header."""
        for idx, row in raw_df.iterrows():
            non_null = row.dropna()
            # A good header row has multiple non-numeric string values
            string_vals = [v for v in non_null if isinstance(v, str)]
            if len(string_vals) >= max(2, len(non_null) // 2):
                return idx
        return 0  # fallback: treat row 0 as header

    def load_document(self, file: str | bytes, filename: str, id=None):
        if isinstance(file, str):
            xls = pd.ExcelFile(file)
        else:
            xls = pd.ExcelFile(BytesIO(file))

        self.documents = self._parse_xls(xls, filename, id)

    def get_document(self):
        return self.documents

    def get_full_content(self):
        return " ".join(doc.page_content for doc in self.documents)
