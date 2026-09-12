from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
import yaml
from pydantic import BaseModel, ConfigDict, Field

from kb2_runtime.plugins.contracts import PluginDescriptor, RunnerType
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.retrieval.contracts import HierarchyRetrieverConfig, RetrieverConfig
from kb2_runtime.fusion.contracts import FusionConfig
from kb2_runtime.evidence.contracts import ContextAssemblerConfig
from kb2_runtime.query_profiles import QueryArtifactBinding, QueryProfileCompiler, QueryProfileError, QueryProfileErrorCode, QueryProfileParser
from kb2_runtime.trace.contracts import ArtifactReference


class RetrieveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    mode: str


class ContextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    budget: int = Field(ge=1, le=32)


class EmptyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def registry() -> PluginRegistry:
    value = PluginRegistry(lambda _: True, lambda _: True)
    for plugin_id, config, inputs, outputs in (
        ("query.retrieve@1", RetrieveConfig, (("opaque.bytes", "v1"), ("search.index.result", "v1")), (("retrieval.candidate.set", "v1"),)),
        ("query.context@1", ContextConfig, (("retrieval.candidate.set", "v1"),), (("opaque.bytes", "v1"),)),
        ("query.verify@1", EmptyConfig, (("opaque.bytes", "v1"),), (("opaque.bytes", "v1"),)),
        ("query.repair@1", EmptyConfig, (("opaque.bytes", "v1"),), (("opaque.bytes", "v1"),)),
        ("query.final@1", EmptyConfig, (("evidence.set", "v1"),), (("opaque.bytes", "v1"),)),
    ):
        names = {"query.retrieve@1": (("question", "opaque.bytes", "v1"), ("index", "search.index.result", "v1"), ("candidates", "retrieval.candidate.set", "v1")), "query.context@1": (("candidates", "retrieval.candidate.set", "v1"), ("evidence", "opaque.bytes", "v1")), "query.verify@1": (("evidence", "opaque.bytes", "v1"), ("verdict", "opaque.bytes", "v1")), "query.repair@1": (("question", "opaque.bytes", "v1"), ("repaired", "opaque.bytes", "v1")), "query.final@1": (("evidence", "evidence.set", "v1"), ("final", "opaque.bytes", "v1"))}[plugin_id]
        value.register(PluginDescriptor(plugin_id=plugin_id, kind="query", implementation_digest=("a" if plugin_id == "query.retrieve@1" else "b") * 64, runner=RunnerType.IN_PROCESS, configuration_schema=config.model_json_schema(), input_schemas=inputs, output_schemas=outputs, input_ports=tuple({"name": name, "artifact_type": typ, "schema_revision": rev} for name, typ, rev in names[:len(inputs)]), output_ports=tuple({"name": name, "artifact_type": typ, "schema_revision": rev} for name, typ, rev in names[len(inputs):]), timeout_seconds=1), lambda: None, config)
    for plugin_id, config in (("retriever.keyword@1", RetrieverConfig), ("retriever.vector@1", RetrieverConfig), ("retriever.table@1", RetrieverConfig), ("retriever.metadata@1", RetrieverConfig), ("retriever.hierarchy@1", HierarchyRetrieverConfig)):
        value.register(PluginDescriptor(plugin_id=plugin_id, kind="retriever", implementation_digest="c" * 64, runner=RunnerType.IN_PROCESS, configuration_schema=config.model_json_schema(), input_schemas=(("opaque.bytes", "v1"), ("search.index.result", "v1")), output_schemas=(("retrieval.candidate.set", "v1"),), input_ports=({"name": "question", "artifact_type": "opaque.bytes", "schema_revision": "v1"}, {"name": "index", "artifact_type": "search.index.result", "schema_revision": "v1"}), output_ports=({"name": "candidates", "artifact_type": "retrieval.candidate.set", "schema_revision": "v1"},), timeout_seconds=1), lambda: None, config)
    value.register(PluginDescriptor(plugin_id="fusion.reciprocal-rank@1", kind="fusion", implementation_digest="d" * 64, runner=RunnerType.IN_PROCESS, configuration_schema=FusionConfig.model_json_schema(), input_schemas=(("retrieval.candidate.set", "v1"),), output_schemas=(("fusion.candidate.set", "v1"),), input_ports=({"name": "candidate_sets", "artifact_type": "retrieval.candidate.set", "schema_revision": "v1", "min_items": 1, "max_items": 8},), output_ports=({"name": "fused_candidates", "artifact_type": "fusion.candidate.set", "schema_revision": "v1"},), timeout_seconds=1), lambda: None, FusionConfig)
    for plugin_id, candidate_type in (("context.from-retrieval@1", "retrieval.candidate.set"), ("context.from-fusion@1", "fusion.candidate.set"), ("context.from-rerank@1", "rerank.candidate.set")):
        value.register(PluginDescriptor(plugin_id=plugin_id, kind="context", implementation_digest="e" * 64, runner=RunnerType.IN_PROCESS, configuration_schema=ContextAssemblerConfig.model_json_schema(), input_schemas=((candidate_type, "v1"), ("search.index.result", "v1")), output_schemas=(("evidence.set", "v1"),), input_ports=({"name": "candidates", "artifact_type": candidate_type, "schema_revision": "v1"}, {"name": "index", "artifact_type": "search.index.result", "schema_revision": "v1"}), output_ports=({"name": "evidence", "artifact_type": "evidence.set", "schema_revision": "v1"},), timeout_seconds=1), lambda: None, ContextAssemblerConfig)
    return value


def artifact(digest: str = "c" * 64) -> QueryArtifactBinding:
    return QueryArtifactBinding.from_reference(ArtifactReference(id=UUID("12345678-1234-5678-1234-567812345678"), artifact_type="search.index.result", schema_revision="v1", content_digest=digest, byte_size=12, summary="index"))


def compile_source(source: str):
    return QueryProfileCompiler(registry()).compile(QueryProfileParser.parse(source, "application/json"), artifact())


def test_json_mapping_order_and_artifact_binding_have_stable_identity() -> None:
    source = (Path("tests/fixtures/query_profiles/text-hybrid.json").read_text())
    first = compile_source(source).get("text-hybrid")
    second = compile_source(json.dumps(json.loads(source), indent=2)).get("text-hybrid")
    assert first.digest == second.digest
    assert first.canonical_payload["search_artifact"]["content_digest"] == "c" * 64
    changed = QueryProfileCompiler(registry()).compile(QueryProfileParser.parse(source, "application/json"), artifact("d" * 64)).get("text-hybrid")
    assert changed.digest != first.digest


def test_equivalent_yaml_source_compiles_to_the_same_plan() -> None:
    source = Path("tests/fixtures/query_profiles/text-hybrid.json").read_text()
    json_plan = compile_source(source).get("text-hybrid")
    yaml_profile = QueryProfileParser.parse(yaml.safe_dump(json.loads(source)), "application/yaml")
    yaml_plan = QueryProfileCompiler(registry()).compile(yaml_profile, artifact()).get("text-hybrid")

    assert yaml_plan.canonical_payload == json_plan.canonical_payload
    assert yaml_plan.digest == json_plan.digest


def test_configuration_change_alters_plan_identity() -> None:
    source = Path("tests/fixtures/query_profiles/text-hybrid.json").read_text()
    first = compile_source(source).get("text-hybrid")
    changed = json.loads(source)
    changed["profiles"][0]["stages"][0]["configuration"]["limit"] = 7

    assert compile_source(json.dumps(changed)).get("text-hybrid").digest != first.digest


def test_all_baseline_families_are_configuration_over_common_stages() -> None:
    names = ["text-hybrid", "hierarchy-aware", "table-aware", "high-precision-fact", "section-summary"]
    plans = [compile_source(Path(f"tests/fixtures/query_profiles/{name}.json").read_text()).get(name) for name in names]
    assert {plan.canonical_payload["stages"][0]["plugin_id"] for plan in plans} == {"retriever.keyword@1", "retriever.hierarchy@1", "retriever.table@1", "retriever.metadata@1"}


def test_repeated_fusion_port_preserves_source_order_and_rejects_invalid_bindings() -> None:
    source = json.loads(Path("tests/fixtures/query_profiles/text-hybrid.json").read_text())

    compiled = compile_source(json.dumps(source)).get("text-hybrid")
    resolved_fusion = next(stage for stage in compiled.canonical_payload["stages"] if stage["stage_id"] == "fuse")
    assert resolved_fusion["inputs"] == [{
        "name": "candidate_sets",
        "source": ["keyword.candidates", "vector.candidates"],
        "artifact_type": "retrieval.candidate.set",
        "schema_revision": "v1",
    }]

    cases = [
        ([], QueryProfileErrorCode.PORT_UNBOUND),
        (["keyword.candidates", "keyword.candidates"], QueryProfileErrorCode.PORT_UNBOUND),
        (["keyword.candidates"] * 9, QueryProfileErrorCode.PORT_UNBOUND),
        (["query.question"], QueryProfileErrorCode.SCHEMA_INCOMPATIBLE),
        (["final.final"], QueryProfileErrorCode.GRAPH_CYCLE),
    ]
    for candidate_sets, code in cases:
        invalid = json.loads(json.dumps(source))
        invalid["profiles"][0]["stages"][2]["inputs"] = {"candidate_sets": candidate_sets}
        with pytest.raises(QueryProfileError) as raised:
            compile_source(json.dumps(invalid))
        assert raised.value.code is code


@pytest.mark.parametrize(("change", "code"), [
    (lambda value: value["profiles"][0]["stages"][0].update(plugin_id="missing@1"), QueryProfileErrorCode.PLUGIN_UNKNOWN),
    (lambda value: value["profiles"][0]["stages"][0]["inputs"].update(question="final.final"), QueryProfileErrorCode.GRAPH_CYCLE),
    (lambda value: value["profiles"][0]["stages"][1].update(when={"eq": ["unknown", True]}), QueryProfileErrorCode.CONDITION_UNSUPPORTED),
    (lambda value: value["profiles"][0]["stages"][4]["inputs"].update(evidence="query.question"), QueryProfileErrorCode.SCHEMA_INCOMPATIBLE),
])
def test_compiler_errors_are_safe_and_addressable(change, code) -> None:
    value = json.loads(Path("tests/fixtures/query_profiles/text-hybrid.json").read_text())
    change(value)
    with pytest.raises(QueryProfileError) as raised:
        compile_source(json.dumps(value))
    assert raised.value.code is code and raised.value.location.startswith("/") and len(raised.value.location) <= 256


def test_compiler_rejects_selection_rules_that_can_match_together() -> None:
    value = json.loads(Path("tests/fixtures/query_profiles/text-hybrid.json").read_text())
    value["selection_rules"] = [
        {
            "rule_id": "table-fact",
            "question_class": "fact",
            "when": {"eq": ["has_tables", True]},
            "profile_id": "text-hybrid",
        },
        {
            "rule_id": "hierarchy-fact",
            "question_class": "fact",
            "when": {"eq": ["has_hierarchy", True]},
            "profile_id": "text-hybrid",
        },
    ]

    with pytest.raises(QueryProfileError) as raised:
        compile_source(json.dumps(value))

    assert raised.value.code is QueryProfileErrorCode.SELECTION_INVALID


def test_repair_inputs_cannot_reintroduce_question_or_retrieval_data() -> None:
    with pytest.raises(QueryProfileError) as raised:
        QueryProfileCompiler._validate_repair_inputs(
            [{"name": "question", "source": "query.question"}],
            [{"stage_id": "context", "kind": "context", "outputs": [{"name": "evidence"}]}, {"stage_id": "verify", "kind": "verify", "outputs": [{"name": "verdict"}]}],
            "/profiles/text-hybrid/stages/repair",
        )

    assert raised.value.code is QueryProfileErrorCode.PORT_UNBOUND
    assert raised.value.location.endswith("/inputs/question")


def test_compilation_rejects_a_repair_stage_bound_to_raw_question_input() -> None:
    source = json.dumps({
        "schema_version": "v1",
        "default_profile_id": "raw-repair",
        "profiles": [{
            "profile_id": "raw-repair",
            "stages": [
                {"stage_id": "retrieve", "kind": "retrieve", "plugin_id": "query.retrieve@1", "configuration": {"mode": "hybrid"}, "inputs": {"question": "query.question", "index": "search.index"}, "outputs": ["candidates"]},
                {"stage_id": "context", "kind": "context", "plugin_id": "query.context@1", "configuration": {"budget": 8}, "inputs": {"candidates": "retrieve.candidates"}, "outputs": ["evidence"]},
                {"stage_id": "verify", "kind": "verify", "plugin_id": "query.verify@1", "inputs": {"evidence": "context.evidence"}, "outputs": ["verdict"]},
                {"stage_id": "repair", "kind": "repair", "plugin_id": "query.repair@1", "max_attempts": 1, "inputs": {"question": "query.question"}, "outputs": ["repaired"]},
                {"stage_id": "final", "kind": "final_state", "plugin_id": "query.final@1", "inputs": {"evidence": "context.evidence"}, "outputs": ["final"]},
            ],
        }],
    })

    with pytest.raises(QueryProfileError) as raised:
        compile_source(source)

    assert raised.value.code is QueryProfileErrorCode.PORT_UNBOUND
    assert raised.value.location.endswith("/inputs/question")
