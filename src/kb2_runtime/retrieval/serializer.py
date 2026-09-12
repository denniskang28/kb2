from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import RetrievalCandidateSet


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value.model_dump(mode="json") if hasattr(value, "model_dump") else value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def candidate_id(index_id: str, contributor_id: str, chunk_id: str) -> str:
    return "rcd_" + hashlib.sha256(canonical_bytes({"index": index_id, "contributor": contributor_id, "chunk": chunk_id})).hexdigest()[:32]


def candidate_set_id(
    index_binding: Any, index_id: str, plugin_id: str, implementation_digest: str,
    contributor_id: str, configuration_digest: str, filtered_count: int, candidates: tuple[Any, ...],
) -> str:
    identity = {
        "index": index_binding.model_dump(mode="json") if hasattr(index_binding, "model_dump") else index_binding,
        "index_id": index_id,
        "plugin": plugin_id,
        "implementation": implementation_digest,
        "contributor": contributor_id,
        "configuration": configuration_digest,
        "filtered_count": filtered_count,
        "candidates": [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in candidates],
    }
    return "rcs_" + hashlib.sha256(canonical_bytes(identity)).hexdigest()[:32]


def retrieval_candidate_set_bytes(value: RetrievalCandidateSet) -> bytes:
    return canonical_bytes(value)
