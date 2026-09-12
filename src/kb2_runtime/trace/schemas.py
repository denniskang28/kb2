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
    ("generated.answer", "v1"),
    ("verification.result", "v1"),
    ("final.response", "v1"),
    ("golden.dataset.snapshot", "v1"),
    ("judge.calibration.snapshot", "v1"),
    ("judge.result", "v1"),
    ("judge.calibration.report", "v1"),
    ("metric.report", "v1"),
    ("metric.aggregate", "v1"),
    ("evaluation.input.catalog", "v1"),
    ("evaluation.manifest", "v1"),
    ("evaluation.gate.report", "v1"),
    ("evaluation.operation.report", "v1"),
    ("evaluation.report.catalog", "v1"),
    ("evaluation.report", "v1"),
    ("evaluation.comparison", "v1"),
    ("evaluation.replay.observation", "v1"),
    ("evaluation.navigation.index", "v1"),
})


def schema_is_supported(artifact_type: str, schema_revision: str) -> bool:
    return (artifact_type, schema_revision) in SUPPORTED_ARTIFACT_SCHEMAS
