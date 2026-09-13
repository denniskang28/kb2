from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ConfigDict

from kb2_runtime.ingestion_profiles import ProfileCompiler, ProfileError, ProfileErrorCode, ProfileParser
from kb2_runtime.plugins.bootstrap import SyntheticTransform, bootstrap_registry
from kb2_runtime.plugins.contracts import PluginDescriptor, RunnerType


AXES = ("extraction", "structure", "chunking", "enrichment", "embedding", "indexing")


def profile(plugin_id: str = "transform.synthetic@1", condition: dict | None = None) -> dict:
    axes, previous = {}, "document.source"
    for axis in AXES:
        axes[axis] = {"candidates": [{"plugin_id": plugin_id, "configuration": {"suffix": ""}, "inputs": {"source": previous}, "outputs": ["result"], "when": condition, "accept_quality": ["PASS", "WARN", "FAIL"]}]}
        previous = f"{axis}.result"
    return {"schema_version": "v1", "default_profile_id": "default", "profiles": [{"profile_id": "default", "axes": axes}]}


def compiled(value: dict):
    parsed = ProfileParser.parse(json.dumps(value), "application/json")
    return ProfileCompiler(bootstrap_registry()).compile(parsed)


def test_json_yaml_and_mapping_order_compile_to_same_complete_plan() -> None:
    value = profile()
    first = compiled(value).get("default")
    yaml_text = json.dumps(value).replace("{", "{ ").replace(",", ", ")
    second = ProfileCompiler(bootstrap_registry()).compile(ProfileParser.parse(yaml_text, "application/yaml")).get("default")
    assert first.digest == second.digest and first.canonical_payload == second.canonical_payload
    assert [stage["axis"] for stage in first.canonical_payload["stages"]] == list(AXES)


def test_profile_axes_can_be_reordered_by_persistent_json_storage() -> None:
    value = profile()
    axes = value["profiles"][0]["axes"]
    value["profiles"][0]["axes"] = {name: axes[name] for name in reversed(AXES)}
    plan = compiled(value).get("default").canonical_payload
    assert [stage["axis"] for stage in plan["stages"]] == list(AXES)


def test_compiled_plan_preserves_conditional_fallback_order_and_acceptance_policy() -> None:
    value = profile()
    axis = value["profiles"][0]["axes"]["extraction"]
    axis["candidates"] = [
        {
            "plugin_id": "transform.synthetic@1",
            "configuration": {"suffix": "preferred"},
            "inputs": {"source": "document.source"},
            "outputs": ["result"],
            "when": {"eq": ["document.extension", "pdf"]},
            "accept_quality": ["PASS"],
        },
        {
            "plugin_id": "transform.synthetic@1",
            "configuration": {"suffix": "fallback"},
            "inputs": {"source": "document.source"},
            "outputs": ["result"],
            "accept_quality": ["PASS", "WARN", "FAIL"],
        },
    ]
    candidates = compiled(value).get("default").canonical_payload["stages"][0]["candidates"]
    assert [candidate["configuration"]["suffix"] for candidate in candidates] == ["preferred", "fallback"]
    assert candidates[0]["when"] == {"eq": ["document.extension", "pdf"]}
    assert candidates[0]["accept_quality"] == ["PASS"]
    assert candidates[1]["accept_quality"] == ["PASS", "WARN", "FAIL"]


@pytest.mark.parametrize(("change", "code"), [
    (lambda value: value["profiles"][0]["axes"]["extraction"]["candidates"][0].update(plugin_id="missing.plugin@1"), ProfileErrorCode.PLUGIN_UNKNOWN),
    (lambda value: value["profiles"][0]["axes"]["extraction"]["candidates"][0]["inputs"].update(source="indexing.result"), ProfileErrorCode.GRAPH_CYCLE),
    (lambda value: value["profiles"][0]["axes"]["extraction"]["candidates"][0]["inputs"].update(source="document.unknown"), ProfileErrorCode.PORT_UNBOUND),
    (lambda value: value["profiles"][0]["axes"]["extraction"]["candidates"][0].update(when={"eq": ["quality.extraction.signal", "PASS"]}), ProfileErrorCode.CONDITION_UNSUPPORTED),
    (lambda value: value["profiles"][0]["axes"]["extraction"]["candidates"][0].update(when={"gte": ["document.byte_size", "large"]}), ProfileErrorCode.CONDITION_UNSUPPORTED),
])
def test_semantic_errors_are_bounded(change: object, code: ProfileErrorCode) -> None:
    value = profile()
    change(value)  # type: ignore[operator]
    with pytest.raises(ProfileError) as raised:
        compiled(value)
    assert raised.value.code is code and raised.value.location.startswith("/") and len(raised.value.location) <= 256


@pytest.mark.parametrize(("payload", "media_type"), [
    ('{"schema_version":"v1","command":"x"}', "application/json"),
    ('schema_version: v1\ndefault_profile_id: default\nprofiles: &p []', "application/yaml"),
    ('{"schema_version":"v1","default_profile_id":"${HOME}"}', "application/json"),
    ('{"schema_version":"v1","default_profile_id":"default","byte_size":NaN}', "application/json"),
    ('schema_version: v1\ndefault_profile_id: default\nbyte_size: .inf', "application/yaml"),
])
def test_parser_rejects_unsafe_content(payload: str, media_type: str) -> None:
    with pytest.raises(ProfileError) as raised:
        ProfileParser.parse(payload, media_type)  # type: ignore[arg-type]
    assert raised.value.code in {ProfileErrorCode.PARSE_INVALID, ProfileErrorCode.UNSAFE_CONTENT}


def test_compiler_rejects_overlapping_preflight_rules_before_resolution() -> None:
    value = profile()
    value["preflight_rules"] = [
        {"rule_id": "pdf", "when": {"eq": ["document.extension", "pdf"]}, "profile_id": "default"},
        {"rule_id": "pdf-large", "when": {"gte": ["document.byte_size", 1]}, "profile_id": "default"},
    ]
    with pytest.raises(ProfileError) as raised:
        compiled(value)
    assert raised.value.code is ProfileErrorCode.SELECTION_INVALID
    assert raised.value.location == "/preflight_rules/0"


class ExtensionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    suffix: str = ""


def test_registered_extension_compiles_without_dispatch_changes() -> None:
    registry = bootstrap_registry()
    descriptor = PluginDescriptor(plugin_id="transform.extension@1", kind="transform", implementation_digest="b" * 64, runner=RunnerType.IN_PROCESS, configuration_schema=ExtensionConfig.model_json_schema(), input_schemas=(("opaque.bytes", "v1"),), output_schemas=(("opaque.bytes", "v1"),), input_ports=({"name": "source", "artifact_type": "opaque.bytes", "schema_revision": "v1"},), output_ports=({"name": "result", "artifact_type": "opaque.bytes", "schema_revision": "v1"},), timeout_seconds=1)
    registry.register(descriptor, SyntheticTransform, ExtensionConfig)
    source = ProfileParser.parse(json.dumps(profile("transform.extension@1")), "application/json")
    assert ProfileCompiler(registry).compile(source).get("default").canonical_payload["stages"][0]["candidates"][0]["plugin_id"] == "transform.extension@1"


def test_explicit_sub_stages_compile_parser_normalizer_and_projector_indexer_transitions() -> None:
    def candidate(plugin_id: str, inputs: dict[str, str], outputs: list[str], configuration: dict | None = None) -> dict:
        return {"plugin_id": plugin_id, "configuration": configuration or {}, "inputs": inputs, "outputs": outputs, "accept_quality": ["PASS", "WARN", "FAIL"]}

    axes = {
        "extraction": {"sub_stages": [
            {"stage_id": "parse", "candidates": [candidate("parser.native-ooxml@1", {"source": "document.source"}, ["provider_result"])], "on_exhausted": "fail"},
            {"stage_id": "normalize", "candidates": [candidate("normalizer.native-ooxml@1", {"provider_result": "extraction.parse.provider_result"}, ["canonical_document"])], "on_exhausted": "fail"},
        ]},
        "structure": {"sub_stages": [{"stage_id": "main", "candidates": [candidate("structure.canonical@1", {"canonical_document": "extraction.normalize.canonical_document"}, ["structured_document"], {"strategy": "hierarchy"})], "on_exhausted": "fail"}]},
        "chunking": {"sub_stages": [{"stage_id": "main", "candidates": [candidate("chunker.canonical@1", {"canonical_document": "structure.main.structured_document"}, ["chunk_set"], {"strategy": "fixed_window", "max_tokens": 64})], "on_exhausted": "fail"}]},
        "enrichment": {"sub_stages": [{"stage_id": "main", "candidates": [candidate("enricher.chunk-metadata@1", {"chunk_set": "chunking.main.chunk_set"}, ["enriched_chunk_set"], {"fields": {"corpus": "fixture"}})], "on_exhausted": "fail"}]},
        "embedding": {"sub_stages": [{"stage_id": "main", "candidates": [candidate("embedder.hashing@1", {"chunk_set": "enrichment.main.enriched_chunk_set"}, ["embedding_set"])], "on_exhausted": "fail"}]},
        "indexing": {"sub_stages": [
            {"stage_id": "project", "candidates": [candidate("search-document.projector@1", {"chunk_set": "enrichment.main.enriched_chunk_set", "embedding_set": "embedding.main.embedding_set"}, ["search_document_set"])], "on_exhausted": "fail"},
            {"stage_id": "index", "candidates": [candidate("indexer.local-hybrid@1", {"search_document_set": "indexing.project.search_document_set"}, ["search_index_result"])], "on_exhausted": "fail"},
        ]},
    }
    payload = {"schema_version": "v1", "default_profile_id": "native", "document_inputs": {"source": {"artifact_type": "source.native-ooxml", "schema_revision": "v1"}}, "profiles": [{"profile_id": "native", "axes": axes}]}
    plan = ProfileCompiler(bootstrap_registry()).compile(ProfileParser.parse(json.dumps(payload), "application/json")).get("native").canonical_payload
    assert [item["stage_id"] for item in plan["stages"][0]["sub_stages"]] == ["parse", "normalize"]
    assert plan["stages"][5]["sub_stages"][0]["candidates"][0]["inputs"][1]["source"] == "embedding.main.embedding_set"
    assert plan["stages"][5]["sub_stages"][1]["candidates"][0]["inputs"][0]["source"] == "indexing.project.search_document_set"


def test_profile_rejects_duplicate_sub_stage_ids_within_one_axis() -> None:
    value = profile()
    axis = value["profiles"][0]["axes"]["extraction"]
    candidates = axis.pop("candidates")
    axis.pop("on_exhausted", None)
    axis["sub_stages"] = [
        {"stage_id": "duplicate", "candidates": candidates, "on_exhausted": "fail"},
        {"stage_id": "duplicate", "candidates": candidates, "on_exhausted": "fail"},
    ]
    with pytest.raises(ProfileError) as raised:
        ProfileParser.parse(json.dumps(value), "application/json")
    assert raised.value.code is ProfileErrorCode.PARSE_INVALID
