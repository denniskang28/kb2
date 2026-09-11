from __future__ import annotations

import json

from kb2_runtime.ingestion_profiles import ProfileCompiler, ProfileParser
from kb2_runtime.ingestion_profiles.contracts import AXES
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from tests.contract.test_structure import fixture, invoke


def profile(strategy: str, fallback: bool = False) -> dict[str, object]:
    candidate = {"plugin_id": "structure.canonical@1", "configuration": {"strategy": strategy}, "inputs": {"canonical_document": "document.source"}, "outputs": ["structured_document"], "accept_quality": ["PASS"]}
    axes = {}
    for axis in AXES:
        candidates = [candidate]
        if axis == "structure" and fallback:
            candidates = [candidate, {**candidate, "configuration": {"strategy": "table"}, "accept_quality": ["PASS", "WARN"]}]
        axes[axis] = {"candidates": candidates, "on_exhausted": "fail"}
    return {"schema_version": "v1", "default_profile_id": "structure", "document_inputs": {"source": {"artifact_type": "canonical.document", "schema_revision": "v1"}}, "profiles": [{"profile_id": "structure", "axes": axes}]}


def compile(value: dict[str, object]) -> dict[str, object]:
    parsed = ProfileParser.parse(json.dumps(value), "application/json")
    return ProfileCompiler(bootstrap_registry()).compile(parsed).get("structure").canonical_payload


def test_three_characteristics_reuse_the_same_structure_component_with_configuration_only() -> None:
    plans = [compile(profile(strategy)) for strategy in ("hierarchy", "layout", "table")]
    candidates = [plan["stages"][1]["candidates"][0] for plan in plans]
    assert {candidate["plugin_id"] for candidate in candidates} == {"structure.canonical@1"}
    assert {candidate["implementation_digest"] for candidate in candidates} == {"f" * 64}
    assert [candidate["configuration"]["strategy"] for candidate in candidates] == ["hierarchy", "layout", "table"]
    fixture_names = ("long-hierarchy-canonical.json", "pdf-layout-canonical.json", "table-heavy-canonical.json")
    for candidate, fixture_name in zip(candidates, fixture_names, strict=True):
        output, stored, _, runs = invoke(fixture(fixture_name), candidate["configuration"]["strategy"])
        assert stored.producing_plugin_id == candidate["plugin_id"]
        assert not runs.failures and output


def test_declared_fallback_order_and_acceptance_policy_are_serialized_without_execution() -> None:
    candidates = compile(profile("hierarchy", fallback=True))["stages"][1]["candidates"]
    assert [candidate["configuration"]["strategy"] for candidate in candidates] == ["hierarchy", "table"]
    assert [candidate["accept_quality"] for candidate in candidates] == [["PASS"], ["PASS", "WARN"]]
