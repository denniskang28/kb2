from __future__ import annotations
import hashlib
import json
from typing import Any
from .contracts import EvidenceSet


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value.model_dump(mode="json") if hasattr(value, "model_dump") else value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False, default=lambda item: item.model_dump(mode="json")).encode("ascii")


def citation_key(document_id: str, chunk_id: str, element_ids: tuple[Any, ...], locators: tuple[Any, ...]) -> str:
    return "cit_" + hashlib.sha256(canonical_bytes({"document": document_id, "chunk": chunk_id, "elements": element_ids, "locators": locators})).hexdigest()[:32]


def evidence_id(citation: str) -> str:
    return "evd_" + hashlib.sha256(canonical_bytes({"citation": citation})).hexdigest()[:32]


def evidence_set_id(source: str, index: Any, index_id: str, plugin: str, implementation: str, configuration: str, items: tuple[Any, ...], decisions: tuple[Any, ...], shortage: Any) -> str:
    value = {"source": source, "index": index.model_dump(mode="json"), "index_id": index_id, "plugin": plugin, "implementation": implementation, "configuration": configuration, "items": items, "decisions": decisions, "shortage": shortage}
    return "evs_" + hashlib.sha256(canonical_bytes(value)).hexdigest()[:32]


def evidence_set_bytes(value: EvidenceSet) -> bytes: return canonical_bytes(value)
