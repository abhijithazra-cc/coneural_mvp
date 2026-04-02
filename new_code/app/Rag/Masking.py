# # from dataclasses import dataclass, field
# # from typing import Dict, List, Optional
# # import hashlib
# # import os
# # from langchain_core.documents import Document
# # from presidio_analyzer import AnalyzerEngine, RecognizerResult
# # from presidio_analyzer.predefined_recognizers import (
# #     InAadhaarRecognizer,
# #     InPanRecognizer,
# # )

# # # ───────────────────────── Policies ─────────────────────────

# # DEFAULT_ENTITIES: List[str] = [
# #     "PERSON",
# #     "EMAIL_ADDRESS",
# #     "PHONE_NUMBER",
# #     "US_SSN",
# #     "IN_AADHAAR",
# #     "IN_PAN",
# #     "CREDIT_CARD",
# #     "IBAN_CODE",
# #     "US_BANK_NUMBER",
# #     "DATE_TIME",
# #     "LOCATION",
# #     "IP_ADDRESS",
# # ]


# # @dataclass
# # class PiiPolicy:
# #     """
# #     strategy:
# #         - "synthetic"        → __PERSON_1__
# #         - "hash"             → __PERSON_ab12cd__
# #         - "synthetic+hash"   → __PERSON_1_ab12cd__
# #     """

# #     entities: List[str] = field(default_factory=lambda: DEFAULT_ENTITIES.copy())
# #     strategy: str = "synthetic+hash"


# # @dataclass
# # class PiiMaskingState:
# #     """
# #     mapping: placeholder -> original
# #     reverse: original -> placeholder
# #     """

# #     mapping: Dict[str, str] = field(default_factory=dict)
# #     reverse: Dict[str, str] = field(default_factory=dict)
# #     policy: Optional[PiiPolicy] = None


# # # ───────────────────────── Masking Class ─────────────────────────


# # class Masking:
# #     def __init__(self, policy: Optional[PiiPolicy] = None):
# #         self.policy = policy or self.get_default_policy()

# #         self._hash_secret = os.getenv("PII_HASH_SECRET", "change-me-please")

# #         self._analyzer = AnalyzerEngine()
# #         self._analyzer.registry.add_recognizer(InAadhaarRecognizer())
# #         self._analyzer.registry.add_recognizer(InPanRecognizer())

# #     # ───────────────────────── Policy helpers ─────────────────────────

# #     @staticmethod
# #     def get_default_policy() -> PiiPolicy:
# #         strategy = os.getenv("PII_DEFAULT_STRATEGY", "synthetic+hash")
# #         return PiiPolicy(
# #             entities=DEFAULT_ENTITIES.copy(),
# #             strategy=strategy,
# #         )

# #     # ───────────────────────── Internal helpers ─────────────────────────

# #     def _hash_value(self, original: str, entity_type: str) -> str:
# #         h = hashlib.sha256()
# #         h.update(self._hash_secret.encode("utf-8"))
# #         h.update(entity_type.encode("utf-8"))
# #         h.update(original.encode("utf-8"))
# #         return h.hexdigest()[:8]

# #     def _make_placeholder(
# #         self,
# #         entity_type: str,
# #         original: str,
# #         state: PiiMaskingState,
# #     ) -> str:
# #         policy = state.policy or self.policy
# #         strategy = (policy.strategy or "synthetic+hash").lower()

# #         base_label = entity_type.upper()
# #         count = len(state.mapping) + 1
# #         short_hash = self._hash_value(original, entity_type)

# #         if strategy == "synthetic":
# #             return f"__{base_label}_{count}__"
# #         if strategy == "hash":
# #             return f"__{base_label}_{short_hash}__"
# #         return f"__{base_label}_{count}_{short_hash}__"

# #     def _mask_with_results(
# #         self,
# #         text: str,
# #         results: List[RecognizerResult],
# #         state: PiiMaskingState,
# #     ) -> str:
# #         if not text or not results:
# #             return text

# #         if state.policy is None:
# #             state.policy = self.policy

# #         results = sorted(results, key=lambda r: r.start)

# #         masked_parts: List[str] = []
# #         cur = 0

# #         for r in results:
# #             if r.start < cur:
# #                 continue

# #             masked_parts.append(text[cur : r.start])

# #             original = text[r.start : r.end]
# #             if original in state.reverse:
# #                 placeholder = state.reverse[original]
# #             else:
# #                 placeholder = self._make_placeholder(
# #                     r.entity_type,
# #                     original,
# #                     state,
# #                 )
# #                 state.mapping[placeholder] = original
# #                 state.reverse[original] = placeholder

# #             masked_parts.append(placeholder)
# #             cur = r.end

# #         masked_parts.append(text[cur:])
# #         return "".join(masked_parts)

# #     # ───────────────────────── Public API ─────────────────────────

# #     def mask_text(self, text: str, state: PiiMaskingState) -> str:
# #         if not text:
# #             return text

# #         if state.policy is None:
# #             state.policy = self.policy

# #         results = self._analyzer.analyze(
# #             text=text,
# #             language="en",
# #             entities=self.policy.entities,
# #         )
# #         if not results:
# #             return text

# #         return self._mask_with_results(text, results, state)

# #     def mask_texts(
# #         self,
# #         documents: List[Document],
# #         state: PiiMaskingState,
# #     ) -> List[Document]:
# #         if not documents:
# #             return []

# #         if state.policy is None:
# #             state.policy = self.policy

# #         sentinel = "\n<<__PII_SPLIT_SENTINEL__>>\n"

# #         # 1️⃣ Extract text only (keep order)
# #         texts = [doc.page_content or "" for doc in documents]
# #         full_text = sentinel.join(texts)

# #         # 2️⃣ Analyze once (important for cross-doc consistency)
# #         results = self._analyzer.analyze(
# #             text=full_text,
# #             language="en",
# #             entities=self.policy.entities,
# #         )

# #         if not results:
# #             return documents

# #         # 3️⃣ Mask combined text
# #         masked_full = self._mask_with_results(full_text, results, state)

# #         # 4️⃣ Split back
# #         masked_texts = masked_full.split(sentinel)

# #         # Safety check
# #         if len(masked_texts) != len(documents):
# #             return documents

# #         # 5️⃣ Rebuild Documents (metadata preserved)
# #         masked_documents: List[Document] = []
# #         for doc, masked_content in zip(documents, masked_texts):
# #             masked_documents.append(
# #                 Document(
# #                     page_content=masked_content,
# #                     metadata=doc.metadata.copy() if doc.metadata else {},
# #                 )
# #             )

# #         return masked_documents

# #     def unmask_text(self, text: str, state: PiiMaskingState) -> str:
# #         if not text:
# #             return text

# #         for placeholder, original in state.mapping.items():
# #             text = text.replace(placeholder, original)

# #         return text

# #     def analyze_text(self, text: str) -> List[RecognizerResult]:
# #         if not text:
# #             return []

# #         return self._analyzer.analyze(
# #             text=text,
# #             language="en",
# #             entities=self.policy.entities,
# #         )






# from dataclasses import dataclass, field
# from typing import Dict, List, Optional
# import hashlib
# import re
# import os
# from langchain_core.documents import Document
# from presidio_analyzer import AnalyzerEngine, RecognizerResult
# from presidio_analyzer.predefined_recognizers import (
#     InAadhaarRecognizer,
#     InPanRecognizer,
# )

# # ───────────────────────── Policies ─────────────────────────

# DEFAULT_ENTITIES: List[str] = [
#     "PERSON",
#     "EMAIL_ADDRESS",
#     "PHONE_NUMBER",
#     "US_SSN",
#     "IN_AADHAAR",
#     "IN_PAN",
#     "CREDIT_CARD",
#     "IBAN_CODE",
#     "US_BANK_NUMBER",
#     "DATE_TIME",
#     "LOCATION",
#     "IP_ADDRESS",
# ]


# @dataclass
# class PiiPolicy:
#     """
#     strategy:
#         - "synthetic"        → __PERSON_1__
#         - "hash"             → __PERSON_ab12cd__
#         - "synthetic+hash"   → __PERSON_1_ab12cd__
#     """

#     entities: List[str] = field(default_factory=lambda: DEFAULT_ENTITIES.copy())
#     strategy: str = "synthetic+hash"


# @dataclass
# class PiiMaskingState:
#     """
#     mapping: placeholder -> original
#     reverse: original -> placeholder
#     """

#     mapping: Dict[str, str] = field(default_factory=dict)
#     reverse: Dict[str, str] = field(default_factory=dict)
#     policy: Optional[PiiPolicy] = None


# # ───────────────────────── Masking Class ─────────────────────────


# class Masking:
#     # FIX 1: Class-level singleton to avoid re-initializing AnalyzerEngine on every instantiation
#     _analyzer_instance: Optional[AnalyzerEngine] = None

#     @classmethod
#     def _get_analyzer(cls) -> AnalyzerEngine:
#         if cls._analyzer_instance is None:
#             analyzer = AnalyzerEngine()
#             # FIX 2: Add recognizers only once during singleton creation to avoid duplicates
#             existing = {type(r) for r in analyzer.registry.recognizers}
#             if InAadhaarRecognizer not in existing:
#                 analyzer.registry.add_recognizer(InAadhaarRecognizer())
#             if InPanRecognizer not in existing:
#                 analyzer.registry.add_recognizer(InPanRecognizer())
#             cls._analyzer_instance = analyzer
#         return cls._analyzer_instance

#     def __init__(self, policy: Optional[PiiPolicy] = None):
#         self.policy = policy or self.get_default_policy()
#         self._hash_secret = os.getenv("PII_HASH_SECRET", "change-me-please")
#         self._analyzer = self._get_analyzer()

#     # ───────────────────────── Policy helpers ─────────────────────────

#     @staticmethod
#     def get_default_policy() -> PiiPolicy:
#         strategy = os.getenv("PII_DEFAULT_STRATEGY", "synthetic+hash")
#         return PiiPolicy(
#             entities=DEFAULT_ENTITIES.copy(),
#             strategy=strategy,
#         )

#     # FIX 3: Centralized policy resolution so mask_text and mask_texts behave consistently
#     def _resolve_policy(self, state: PiiMaskingState) -> PiiPolicy:
#         return state.policy or self.policy

#     # ───────────────────────── Internal helpers ─────────────────────────

#     def _hash_value(self, original: str, entity_type: str) -> str:
#         h = hashlib.sha256()
#         h.update(self._hash_secret.encode("utf-8"))
#         h.update(entity_type.encode("utf-8"))
#         h.update(original.encode("utf-8"))
#         return h.hexdigest()[:8]

#     def _make_placeholder(
#         self,
#         entity_type: str,
#         original: str,
#         state: PiiMaskingState,
#     ) -> str:
#         policy = state.policy or self.policy
#         strategy = (policy.strategy or "synthetic+hash").lower()

#         base_label = entity_type.upper()
#         count = len(state.mapping) + 1
#         short_hash = self._hash_value(original, entity_type)

#         if strategy == "synthetic":
#             return f"__{base_label}_{count}__"
#         if strategy == "hash":
#             return f"__{base_label}_{short_hash}__"
#         return f"__{base_label}_{count}_{short_hash}__"

#     def _mask_with_results(
#         self,
#         text: str,
#         results: List[RecognizerResult],
#         state: PiiMaskingState,
#     ) -> str:
#         if not text or not results:
#             return text

#         if state.policy is None:
#             state.policy = self.policy

#         results = sorted(results, key=lambda r: r.start)

#         masked_parts: List[str] = []
#         cur = 0

#         for r in results:
#             if r.start < cur:
#                 continue

#             masked_parts.append(text[cur : r.start])

#             original = text[r.start : r.end]
#             if original in state.reverse:
#                 placeholder = state.reverse[original]
#             else:
#                 placeholder = self._make_placeholder(
#                     r.entity_type,
#                     original,
#                     state,
#                 )
#                 state.mapping[placeholder] = original
#                 state.reverse[original] = placeholder

#             masked_parts.append(placeholder)
#             cur = r.end

#         masked_parts.append(text[cur:])
#         return "".join(masked_parts)

#     # ───────────────────────── Public API ─────────────────────────

#     def mask_text(self, text: str, state: PiiMaskingState) -> str:
#         if not text:
#             return text

#         # FIX 3: Use _resolve_policy for consistency
#         policy = self._resolve_policy(state)
#         if state.policy is None:
#             state.policy = policy

#         results = self._analyzer.analyze(
#             text=text,
#             language="en",
#             entities=policy.entities,
#         )
#         if not results:
#             return text

#         return self._mask_with_results(text, results, state)

#     def mask_texts(
#         self,
#         documents: List[Document],
#         state: PiiMaskingState,
#     ) -> List[Document]:
#         if not documents:
#             return []

#         # FIX 3: Use _resolve_policy for consistency
#         policy = self._resolve_policy(state)
#         if state.policy is None:
#             state.policy = policy

#         # FIX 5: Use offset-based splitting instead of sentinel to avoid fragile split
#         texts = [doc.page_content or "" for doc in documents]

#         # Build offset ranges for each doc in the combined text
#         offsets: List[tuple] = []
#         combined_parts: List[str] = []
#         cur = 0
#         for t in texts:
#             offsets.append((cur, cur + len(t)))
#             combined_parts.append(t)
#             cur += len(t) + 1  # +1 for the newline separator

#         full_text = "\n".join(combined_parts)

#         # Analyze once for cross-doc consistency
#         results = self._analyzer.analyze(
#             text=full_text,
#             language="en",
#             entities=policy.entities,
#         )

#         if not results:
#             return documents

#         # Mask combined text
#         masked_full = self._mask_with_results(full_text, results, state)

#         # Split back using tracked offsets
#         # Recalculate offsets on masked text by splitting on the separator
#         masked_texts = masked_full.split("\n", len(documents) - 1)

#         # Safety check
#         if len(masked_texts) != len(documents):
#             return documents

#         # Rebuild Documents with metadata preserved
#         masked_documents: List[Document] = []
#         for doc, masked_content in zip(documents, masked_texts):
#             masked_documents.append(
#                 Document(
#                     page_content=masked_content,
#                     metadata=doc.metadata.copy() if doc.metadata else {},
#                 )
#             )

#         return masked_documents

#     def unmask_text(self, text: str, state: PiiMaskingState) -> str:
#         if not text or not state.mapping:
#             return text

#         # FIX 4: Single-pass regex replacement instead of O(n×m) repeated str.replace
#         pattern = re.compile("|".join(re.escape(k) for k in state.mapping))
#         return pattern.sub(lambda m: state.mapping[m.group(0)], text)

#     def analyze_text(self, text: str) -> List[RecognizerResult]:
#         if not text:
#             return []

#         return self._analyzer.analyze(
#             text=text,
#             language="en",
#             entities=self.policy.entities,
#         )







from dataclasses import dataclass, field
from email.mime import text
from typing import Dict, List, Optional, Tuple
import hashlib
import re
import os
from langchain_core.documents import Document
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.predefined_recognizers import (
    InAadhaarRecognizer,
    InPanRecognizer,
)

# ───────────────────────── Policies ─────────────────────────

DEFAULT_ENTITIES: List[str] = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "IN_AADHAAR",
    "IN_PAN",
    "CREDIT_CARD",
    "IBAN_CODE",
    "US_BANK_NUMBER",
    "DATE_TIME",
    "LOCATION",
    "IP_ADDRESS",
]


@dataclass
class PiiPolicy:
    """
    strategy:
        - "synthetic"        → __PERSON_1__
        - "hash"             → __PERSON_ab12cd__
        - "synthetic+hash"   → __PERSON_1_ab12cd__
    """

    entities: List[str] = field(default_factory=lambda: DEFAULT_ENTITIES.copy())
    strategy: str = "synthetic+hash"


@dataclass
class PiiMaskingState:
    """
    mapping: placeholder -> original
    reverse: original -> placeholder
    """

    mapping: Dict[str, str] = field(default_factory=dict)
    reverse: Dict[str, str] = field(default_factory=dict)
    policy: Optional[PiiPolicy] = None


# ───────────────────────── Masking Class ─────────────────────────


class Masking:
    # Class-level singleton to avoid re-initializing AnalyzerEngine on every instantiation
    _analyzer_instance: Optional[AnalyzerEngine] = None

    @classmethod
    def _get_analyzer(cls) -> AnalyzerEngine:
        if cls._analyzer_instance is None:
            analyzer = AnalyzerEngine()
            # Add recognizers only once during singleton creation to avoid duplicates
            existing = {type(r) for r in analyzer.registry.recognizers}
            if InAadhaarRecognizer not in existing:
                analyzer.registry.add_recognizer(InAadhaarRecognizer())
            if InPanRecognizer not in existing:
                analyzer.registry.add_recognizer(InPanRecognizer())
            cls._analyzer_instance = analyzer
        return cls._analyzer_instance

    def __init__(self, policy: Optional[PiiPolicy] = None):
        self.policy = policy or self.get_default_policy()
        self._hash_secret = os.getenv("PII_HASH_SECRET", "change-me-please")
        self._analyzer = self._get_analyzer()

    # ───────────────────────── Policy helpers ─────────────────────────

    @staticmethod
    def get_default_policy() -> PiiPolicy:
        strategy = os.getenv("PII_DEFAULT_STRATEGY", "synthetic+hash")
        return PiiPolicy(
            entities=DEFAULT_ENTITIES.copy(),
            strategy=strategy,
        )

    # Centralized policy resolution so mask_text and mask_texts behave consistently
    def _resolve_policy(self, state: PiiMaskingState) -> PiiPolicy:
        return state.policy or self.policy

    # ───────────────────────── Internal helpers ─────────────────────────

    def _hash_value(self, original: str, entity_type: str) -> str:
         h = hashlib.sha256()
         h.update(self._hash_secret.encode("utf-8"))
         h.update(entity_type.encode("utf-8"))
    # FIX: normalize to lowercase so "kolkata" and "Kolkata" get same hash
         h.update(original.lower().encode("utf-8"))
         return h.hexdigest()[:8]

    # def _hash_value(self, original: str, entity_type: str) -> str:
    #     h = hashlib.sha256()
    #     h.update(self._hash_secret.encode("utf-8"))
    #     h.update(entity_type.encode("utf-8"))
    #     h.update(original.encode("utf-8"))
    #     return h.hexdigest()[:8]

    def _make_placeholder(
        self,
        entity_type: str,
        original: str,
        state: PiiMaskingState,
    ) -> str:
        policy = state.policy or self.policy
        strategy = (policy.strategy or "synthetic+hash").lower()

        base_label = entity_type.upper()
        count = len(state.mapping) + 1
        short_hash = self._hash_value(original, entity_type)

        if strategy == "synthetic":
            return f"__{base_label}_{count}__"
        if strategy == "hash":
            return f"__{base_label}_{short_hash}__"
        return f"__{base_label}_{count}_{short_hash}__"

    def _mask_with_results(
    self,
    text: str,
    results: List[RecognizerResult],
    state: PiiMaskingState,
    ) -> str:
       if not text or not results:
          return text

       if state.policy is None:
          state.policy = self.policy

       results = sorted(results, key=lambda r: r.start)

       masked_parts: List[str] = []
       cur = 0

       for r in results:
          if r.start < cur:
             continue
  
          masked_parts.append(text[cur : r.start])

          original = text[r.start : r.end]

        # FIX: case-insensitive lookup so "kolkata" matches "Kolkata" in registry
          original_lower = original.lower()
          existing = next(
            (ph for ph, orig in state.mapping.items()
             if orig.lower() == original_lower),
            None,
        )

          if existing is not None:
            placeholder = existing
          else:
            placeholder = self._make_placeholder(
                r.entity_type,
                original,
                state,
            )
            state.mapping[placeholder] = original
            state.reverse[original] = placeholder

          masked_parts.append(placeholder)
          cur = r.end

       masked_parts.append(text[cur:])
       return "".join(masked_parts)
    # def _mask_with_results(
    #     self,
    #     text: str,
    #     results: List[RecognizerResult],
    #     state: PiiMaskingState,
    # ) -> str:
    #     if not text or not results:
    #         return text

    #     if state.policy is None:
    #         state.policy = self.policy

    #     results = sorted(results, key=lambda r: r.start)

    #     masked_parts: List[str] = []
    #     cur = 0

    #     for r in results:
    #         if r.start < cur:
    #             continue

    #         masked_parts.append(text[cur : r.start])

    #         original = text[r.start : r.end]
    #         if original in state.reverse:
    #             placeholder = state.reverse[original]
    #         else:
    #             placeholder = self._make_placeholder(
    #                 r.entity_type,
    #                 original,
    #                 state,
    #             )
    #             state.mapping[placeholder] = original
    #             state.reverse[original] = placeholder

    #         masked_parts.append(placeholder)
    #         cur = r.end

    #     masked_parts.append(text[cur:])
    #     return "".join(masked_parts)

    # ───────────────────────── Public API ─────────────────────────

    def mask_text(self, text: str, state: PiiMaskingState) -> str:
        if not text:
            return text

        policy = self._resolve_policy(state)
        if state.policy is None:
            state.policy = policy

        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=policy.entities,
        )
        if not results:
            return text

        return self._mask_with_results(text, results, state)

    def mask_texts(
        self,
        documents: List[Document],
        state: PiiMaskingState,
    ) -> List[Document]:
        if not documents:
            return []

        policy = self._resolve_policy(state)
        if state.policy is None:
            state.policy = policy

        texts = [doc.page_content or "" for doc in documents]

        combined_parts: List[str] = []
        cur = 0
        for t in texts:
            combined_parts.append(t)
            cur += len(t) + 1  # +1 for the newline separator

        full_text = "\n".join(combined_parts)

        results = self._analyzer.analyze(
            text=full_text,
            language="en",
            entities=policy.entities,
        )

        if not results:
            return documents

        masked_full = self._mask_with_results(full_text, results, state)

        masked_texts = masked_full.split("\n", len(documents) - 1)

        if len(masked_texts) != len(documents):
            return documents

        masked_documents: List[Document] = []
        for doc, masked_content in zip(documents, masked_texts):
            masked_documents.append(
                Document(
                    page_content=masked_content,
                    metadata=doc.metadata.copy() if doc.metadata else {},
                )
            )

        return masked_documents

    def mask_query_and_docs(
        self,
        query: str,
        documents: List[Document],
        state: PiiMaskingState,
    ) -> Tuple[str, List[Document]]:
        """
        Mask query and documents in ONE shared Presidio session so that
        the same entity value gets the same placeholder in both.

        This is the correct method to use for RAG pipelines — call this
        instead of calling mask_text() and mask_texts() separately.

        Example:
            "Kolkata" in query  → __LOCATION_1_ab12cd__
            "Kolkata" in chunk  → __LOCATION_1_ab12cd__  (identical ✅)

        Use unmask_text() with the same state to restore the LLM answer.

        Returns:
            masked_query      (str)
            masked_documents  (List[Document])
        """
        if not query and not documents:
            return query, documents

        # ── Resolve policy once for the entire session ────────────────────────
        policy = self._resolve_policy(state)
        if state.policy is None:
            state.policy = policy

        # ── Sentinel must never appear in real content ────────────────────────
        SENTINEL = "\n<<__QD_SPLIT__>>\n"

        # ── Step 1: Combine query + all doc texts into one string ─────────────
        doc_texts = [doc.page_content or "" for doc in documents]
        all_parts = [query] + doc_texts
        combined = SENTINEL.join(all_parts)

        # ── Step 2: Single Presidio pass over combined text ───────────────────
        results = self._analyzer.analyze(
            text=combined,
            language="en",
            entities=policy.entities,
        )

        # ── Step 3: Nothing to mask — return originals unchanged ─────────────
        if not results:
            return query, documents

        # ── Step 4: Mask with shared state (same entity → same placeholder) ───
        masked_combined = self._mask_with_results(combined, results, state)

        # ── Step 5: Split back on sentinel ────────────────────────────────────
        # maxsplit = len(documents) so extra sentinels inside content are safe
        parts = masked_combined.split(SENTINEL, len(documents))

        # Safety: if sentinel was somehow corrupted by masking, fall back gracefully
        if len(parts) != len(all_parts):
            return query, documents

        masked_query = parts[0]
        masked_doc_texts = parts[1:]

        # ── Step 6: Rebuild Document objects with metadata preserved ──────────
        masked_documents: List[Document] = []
        for doc, masked_content in zip(documents, masked_doc_texts):
            masked_documents.append(
                Document(
                    page_content=masked_content,
                    metadata=doc.metadata.copy() if doc.metadata else {},
                )
            )

        return masked_query, masked_documents

    def unmask_text(self, text: str, state: PiiMaskingState) -> str:
        if not text or not state.mapping:
            return text

        # Single-pass regex replacement instead of O(n×m) repeated str.replace
        pattern = re.compile("|".join(re.escape(k) for k in state.mapping))
        return pattern.sub(lambda m: state.mapping[m.group(0)], text)

    def analyze_text(self, text: str) -> List[RecognizerResult]:
        if not text:
            return []

        return self._analyzer.analyze(
            text=text,
            language="en",
            entities=self.policy.entities,
        )