from __future__ import annotations
import hashlib
import json
from typing import Any
from .contracts import FusionCandidateSet

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value.model_dump(mode="json") if hasattr(value, "model_dump") else value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False, default=lambda item: item.model_dump(mode="json")).encode("ascii")

def candidate_set_id(index: Any, index_id: str, plugin_id: str, implementation: str, configuration: str, contributors: tuple[str, ...], candidates: tuple[Any, ...]) -> str:
    value = {"index": index.model_dump(mode="json"), "index_id": index_id, "plugin": plugin_id, "implementation": implementation, "configuration": configuration, "contributors": contributors, "candidates": candidates}
    return "fcs_" + hashlib.sha256(canonical_bytes(value)).hexdigest()[:32]

def fusion_candidate_set_bytes(value: FusionCandidateSet) -> bytes: return canonical_bytes(value)
