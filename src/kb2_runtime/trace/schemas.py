from __future__ import annotations


SUPPORTED_ARTIFACT_SCHEMAS: frozenset[tuple[str, str]] = frozenset({
    ("opaque.bytes", "v1"),
    ("provider.parse-result-fixture", "v1"),
    ("source.native-ooxml", "v1"),
    ("source.scanned-ocr-exchange", "v1"),
    ("provider.native-ooxml-result", "v1"),
    ("provider.scanned-ocr-result", "v1"),
    ("canonical.document", "v1"),
    ("chunk.set", "v1"),
    ("embedding.set", "v1"),
    ("search.document.set", "v1"),
    ("search.index.result", "v1"),
    ("retrieval.candidate.set", "v1"),
    ("fusion.candidate.set", "v1"),
    ("rerank.candidate.set", "v1"),
    ("evidence.set", "v1"),
})


def schema_is_supported(artifact_type: str, schema_revision: str) -> bool:
    return (artifact_type, schema_revision) in SUPPORTED_ARTIFACT_SCHEMAS
