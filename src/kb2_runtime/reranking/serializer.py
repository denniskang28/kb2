from __future__ import annotations
import hashlib, json
from typing import Any
from .contracts import RerankedCandidateSet
def canonical_bytes(value: Any) -> bytes: return json.dumps(value.model_dump(mode="json") if hasattr(value, "model_dump") else value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False, default=lambda item: item.model_dump(mode="json")).encode("ascii")
def candidate_set_id(fusion_id: str, index: Any, plugin: str, implementation: str, configuration: str, inputs: tuple[Any, ...], candidates: tuple[Any, ...], decisions: tuple[Any, ...]) -> str:
    return "rrs_" + hashlib.sha256(canonical_bytes({"fusion": fusion_id, "index": index.model_dump(mode="json"), "plugin": plugin, "implementation": implementation, "configuration": configuration, "inputs": inputs, "candidates": candidates, "decisions": decisions})).hexdigest()[:32]
def reranked_candidate_set_bytes(value: RerankedCandidateSet) -> bytes: return canonical_bytes(value)
