from dataclasses import dataclass, field
from typing import Dict, List, Optional
import hashlib
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
    def __init__(self, policy: Optional[PiiPolicy] = None):
        self.policy = policy or self.get_default_policy()

        self._hash_secret = os.getenv("PII_HASH_SECRET", "change-me-please")

        self._analyzer = AnalyzerEngine()
        self._analyzer.registry.add_recognizer(InAadhaarRecognizer())
        self._analyzer.registry.add_recognizer(InPanRecognizer())

    # ───────────────────────── Policy helpers ─────────────────────────

    @staticmethod
    def get_default_policy() -> PiiPolicy:
        strategy = os.getenv("PII_DEFAULT_STRATEGY", "synthetic+hash")
        return PiiPolicy(
            entities=DEFAULT_ENTITIES.copy(),
            strategy=strategy,
        )

    # ───────────────────────── Internal helpers ─────────────────────────

    def _hash_value(self, original: str, entity_type: str) -> str:
        h = hashlib.sha256()
        h.update(self._hash_secret.encode("utf-8"))
        h.update(entity_type.encode("utf-8"))
        h.update(original.encode("utf-8"))
        return h.hexdigest()[:8]

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
            if original in state.reverse:
                placeholder = state.reverse[original]
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

    # ───────────────────────── Public API ─────────────────────────

    def mask_text(self, text: str, state: PiiMaskingState) -> str:
        if not text:
            return text

        if state.policy is None:
            state.policy = self.policy

        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=self.policy.entities,
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

        if state.policy is None:
            state.policy = self.policy

        sentinel = "\n<<__PII_SPLIT_SENTINEL__>>\n"

        # 1️⃣ Extract text only (keep order)
        texts = [doc.page_content or "" for doc in documents]
        full_text = sentinel.join(texts)

        # 2️⃣ Analyze once (important for cross-doc consistency)
        results = self._analyzer.analyze(
            text=full_text,
            language="en",
            entities=self.policy.entities,
        )

        if not results:
            return documents

        # 3️⃣ Mask combined text
        masked_full = self._mask_with_results(full_text, results, state)

        # 4️⃣ Split back
        masked_texts = masked_full.split(sentinel)

        # Safety check
        if len(masked_texts) != len(documents):
            return documents

        # 5️⃣ Rebuild Documents (metadata preserved)
        masked_documents: List[Document] = []
        for doc, masked_content in zip(documents, masked_texts):
            masked_documents.append(
                Document(
                    page_content=masked_content,
                    metadata=doc.metadata.copy() if doc.metadata else {},
                )
            )

        return masked_documents

    def unmask_text(self, text: str, state: PiiMaskingState) -> str:
        if not text:
            return text

        for placeholder, original in state.mapping.items():
            text = text.replace(placeholder, original)

        return text

    def analyze_text(self, text: str) -> List[RecognizerResult]:
        if not text:
            return []

        return self._analyzer.analyze(
            text=text,
            language="en",
            entities=self.policy.entities,
        )
