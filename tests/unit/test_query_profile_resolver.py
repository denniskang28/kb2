from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict

from kb2_runtime.plugins.contracts import PluginDescriptor, RunnerType
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.query_profiles import QueryArtifactBinding, QueryProfileCompiler, QueryProfileParser, QueryProfileResolver, QueryResolutionRequest
from kb2_runtime.trace.contracts import ArtifactReference


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def compiled():
    registry = PluginRegistry(lambda _: True, lambda _: True)
    for plugin_id, ports in (("query.context@1", (("question", "opaque.bytes", "v1"), ("evidence", "opaque.bytes", "v1"))), ("query.final@1", (("evidence", "opaque.bytes", "v1"), ("final", "opaque.bytes", "v1")))):
        registry.register(PluginDescriptor(plugin_id=plugin_id, kind="query", implementation_digest="a" * 64, runner=RunnerType.IN_PROCESS, configuration_schema=Empty.model_json_schema(), input_schemas=((ports[0][1], ports[0][2]),), output_schemas=((ports[1][1], ports[1][2]),), input_ports=({"name": ports[0][0], "artifact_type": ports[0][1], "schema_revision": ports[0][2]},), output_ports=({"name": ports[1][0], "artifact_type": ports[1][1], "schema_revision": ports[1][2]},), timeout_seconds=1), lambda: None, Empty)
    source = '{"schema_version":"v1","default_profile_id":"default","selection_rules":[{"rule_id":"fact","question_class":"fact","profile_id":"fact"},{"rule_id":"table","when":{"eq":["has_tables",true]},"profile_id":"default"}],"profiles":[{"profile_id":"default","stages":[{"stage_id":"context","kind":"context","plugin_id":"query.context@1","inputs":{"question":"query.question"},"outputs":["evidence"]},{"stage_id":"final","kind":"final_state","plugin_id":"query.final@1","inputs":{"evidence":"context.evidence"},"outputs":["final"]}]},{"profile_id":"fact","stages":[{"stage_id":"context","kind":"context","plugin_id":"query.context@1","inputs":{"question":"query.question"},"outputs":["evidence"]},{"stage_id":"final","kind":"final_state","plugin_id":"query.final@1","inputs":{"evidence":"context.evidence"},"outputs":["final"]}]}]}'
    artifact = QueryArtifactBinding.from_reference(ArtifactReference(id=UUID("12345678-1234-5678-1234-567812345678"), artifact_type="search.index.result", schema_revision="v1", content_digest="a" * 64, byte_size=2, summary="index"))
    return QueryProfileCompiler(registry).compile(QueryProfileParser.parse(source, "application/json"), artifact)


def test_resolver_explicit_then_rule_then_default_and_preserves_artifact() -> None:
    value = compiled()
    resolver = QueryProfileResolver()
    assert resolver.resolve(value, QueryResolutionRequest(explicit_profile_id="default", question_class="fact")).selection_tier == "explicit"
    selected = resolver.resolve(value, QueryResolutionRequest(question_class="fact"))
    assert selected.selected_profile_id == "fact" and selected.evaluated_rules[0]["matched"]
    assert resolver.resolve(value, QueryResolutionRequest(question_class="other")).selection_tier == "default"
    assert selected.search_artifact.artifact_id == "12345678-1234-5678-1234-567812345678"


def test_class_rule_precedes_a_matching_conditional_rule() -> None:
    record = QueryProfileResolver().resolve(compiled(), QueryResolutionRequest(question_class="fact", has_tables=True))
    assert record.selected_profile_id == "fact"
    assert record.selection_tier == "class"


def test_resolution_record_has_no_mutation_path() -> None:
    record = QueryProfileResolver().resolve(compiled(), QueryResolutionRequest(question_class="fact"))

    with pytest.raises(TypeError):
        record.observables["question_class"] = "changed"
    with pytest.raises(TypeError):
        record.evaluated_rules[0]["matched"] = False
