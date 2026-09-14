from __future__ import annotations

import asyncio
import copy
import json

from kb2_runtime.ingestion_engine import SourceSubmission
from kb2_runtime.ingestion_profiles import ProfileCompiler, ProfileParser, ResolutionRequest

from tests.contract.test_ingestion_engine import OutcomeConfig, OutcomePlugin, descriptor, engine, profile, registry


def test_three_document_classes_reuse_registered_components_through_distinct_resolved_profiles() -> None:
    profiles = [
        profile(profile_id="native", strategy="hierarchy"),
        profile(profile_id="scanned", strategy="ocr"),
        profile(profile_id="table", strategy="table"),
    ]
    payload = copy.deepcopy(profiles[0])
    payload["profiles"] = [item["profiles"][0] for item in profiles]
    payload["document_class_rules"] = [
        {"rule_id": "native", "document_class": "native", "profile_id": "native"},
        {"rule_id": "scanned", "document_class": "scanned", "profile_id": "scanned"},
        {"rule_id": "table", "document_class": "table", "profile_id": "table"},
    ]
    current = registry()
    compiled = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(payload), "application/json"))
    results = []
    for document_class in ("native", "scanned", "table"):
        runtime, runs = engine(current)
        receipt = asyncio.run(runtime.submit(
            compiled,
            SourceSubmission(content=document_class.encode(), source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename=f"{document_class}.txt", media_type="text/plain"),
            ResolutionRequest(document_class=document_class),
        ))
        results.append((receipt, runs))
    assert [receipt.profile_id for receipt, _ in results] == ["native", "scanned", "table"]
    assert all("indexing.main.result" in receipt.outputs and runs.finished is True for receipt, runs in results)
    assert len({receipt.plan_digest for receipt, _ in results}) == 3


def test_new_document_strategy_runs_from_plugin_registration_and_profile_data_only() -> None:
    current = registry()
    current.register(descriptor("c" * 64, "transform.synthetic-strategy@1"), OutcomePlugin, OutcomeConfig)
    payload = profile(profile_id="synthetic", strategy="synthetic", extraction_plugin="transform.synthetic-strategy@1")
    compiled = ProfileCompiler(current).compile(ProfileParser.parse(json.dumps(payload), "application/json"))
    runtime, runs = engine(current)
    receipt = asyncio.run(runtime.submit(
        compiled,
        SourceSubmission(content=b"synthetic fixture", source_schema={"artifact_type": "opaque.bytes", "schema_revision": "v1"}, filename="synthetic.txt", media_type="text/plain"),
        ResolutionRequest(explicit_profile_id="synthetic"),
    ))
    assert receipt.profile_id == "synthetic" and runs.finished is True
    assert runs.attempts[1]["key"] == "extraction.parse.candidate-1"
