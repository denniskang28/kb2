from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import EmbeddingSet, SearchDocumentSet, SearchIndexResult


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value.model_dump(mode="json") if hasattr(value, "model_dump") else value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def embedding_set_bytes(value: EmbeddingSet) -> bytes: return canonical_bytes(value)
def search_document_set_bytes(value: SearchDocumentSet) -> bytes: return canonical_bytes(value)
def search_index_result_bytes(value: SearchIndexResult) -> bytes: return canonical_bytes(value)
