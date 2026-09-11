from __future__ import annotations

import json

from kb2_runtime.ingestion_profiles import ProfileCompiler, ProfileParser
from kb2_runtime.ingestion_profiles.contracts import AXES
from kb2_runtime.plugins.bootstrap import bootstrap_registry
from kb2_runtime.plugins.contracts import PluginDescriptor, RunnerType
from kb2_runtime.chunking import CanonicalChunkerPlugin, ChunkerConfig


def test_profile_binds_independent_chunking_and_enrichment_axes_by_named_ports() -> None:
    structure = {"plugin_id": "structure.canonical@1", "configuration": {"strategy": "hierarchy"}, "inputs": {"canonical_document": "document.source"}, "outputs": ["structured_document"], "accept_quality": ["PASS"]}
    chunker = {"plugin_id": "chunker.canonical@1", "configuration": {"strategy": "table", "max_tokens": 64}, "inputs": {"canonical_document": "structure.structured_document"}, "outputs": ["chunk_set"], "accept_quality": ["PASS"]}
    enricher = {"plugin_id": "enricher.chunk-metadata@1", "configuration": {"fields": {"corpus": "golden"}}, "inputs": {"chunk_set": "chunking.chunk_set"}, "outputs": ["enriched_chunk_set"], "accept_quality": ["PASS"]}
    axes = {axis: {"candidates": [structure], "on_exhausted": "fail"} for axis in AXES}
    axes["chunking"], axes["enrichment"] = {"candidates": [chunker], "on_exhausted": "fail"}, {"candidates": [enricher], "on_exhausted": "fail"}
    value = {"schema_version": "v1", "default_profile_id": "chunking", "document_inputs": {"source": {"artifact_type": "canonical.document", "schema_revision": "v1"}}, "profiles": [{"profile_id": "chunking", "axes": axes}]}
    plan = ProfileCompiler(bootstrap_registry()).compile(ProfileParser.parse(json.dumps(value), "application/json")).get("chunking").canonical_payload
    assert plan["stages"][2]["candidates"][0]["inputs"][0]["source"] == "structure.structured_document"
    assert plan["stages"][3]["candidates"][0]["inputs"][0]["source"] == "chunking.chunk_set"


def test_compatible_replacement_chunker_is_selected_through_profile_configuration_only() -> None:
    registry = bootstrap_registry()
    registry.register(PluginDescriptor(
        plugin_id="chunker.synthetic@1", kind="chunker", implementation_digest="3" * 64,
        runner=RunnerType.IN_PROCESS, configuration_schema=ChunkerConfig.model_json_schema(),
        input_schemas=(("canonical.document", "v1"),), output_schemas=(("chunk.set", "v1"),),
        input_ports=({"name": "canonical_document", "artifact_type": "canonical.document", "schema_revision": "v1"},),
        output_ports=({"name": "chunk_set", "artifact_type": "chunk.set", "schema_revision": "v1"},),
        quality_signal_names=("chunk_validation", "citation_validation"), timeout_seconds=10,
    ), CanonicalChunkerPlugin, ChunkerConfig)
    structure = {"plugin_id": "structure.canonical@1", "configuration": {"strategy": "hierarchy"}, "inputs": {"canonical_document": "document.source"}, "outputs": ["structured_document"], "accept_quality": ["PASS"]}
    replacement = {"plugin_id": "chunker.synthetic@1", "configuration": {"strategy": "fixed_window", "max_tokens": 64}, "inputs": {"canonical_document": "structure.structured_document"}, "outputs": ["chunk_set"], "accept_quality": ["PASS"]}
    enricher = {"plugin_id": "enricher.chunk-metadata@1", "configuration": {"fields": {"corpus": "golden"}}, "inputs": {"chunk_set": "chunking.chunk_set"}, "outputs": ["enriched_chunk_set"], "accept_quality": ["PASS"]}
    axes = {axis: {"candidates": [structure], "on_exhausted": "fail"} for axis in AXES}
    axes["chunking"], axes["enrichment"] = {"candidates": [replacement], "on_exhausted": "fail"}, {"candidates": [enricher], "on_exhausted": "fail"}
    value = {"schema_version": "v1", "default_profile_id": "replacement", "document_inputs": {"source": {"artifact_type": "canonical.document", "schema_revision": "v1"}}, "profiles": [{"profile_id": "replacement", "axes": axes}]}
    plan = ProfileCompiler(registry).compile(ProfileParser.parse(json.dumps(value), "application/json")).get("replacement").canonical_payload
    candidate = plan["stages"][2]["candidates"][0]
    assert candidate["plugin_id"] == "chunker.synthetic@1"
    assert candidate["implementation_digest"] == "3" * 64
