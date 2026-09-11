from __future__ import annotations


SUPPORTED_ARTIFACT_SCHEMAS: frozenset[tuple[str, str]] = frozenset({
    ("opaque.bytes", "v1"),
    ("provider.parse-result-fixture", "v1"),
    ("canonical.document", "v1"),
})


def schema_is_supported(artifact_type: str, schema_revision: str) -> bool:
    return (artifact_type, schema_revision) in SUPPORTED_ARTIFACT_SCHEMAS
