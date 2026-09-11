from __future__ import annotations

import json

import pytest

from kb2_runtime.ingestion_profiles import ProfileCompiler, ProfileError, ProfileErrorCode, ProfileParser, ProfileResolver, ResolutionRequest
from kb2_runtime.plugins.bootstrap import bootstrap_registry


def source() -> str:
    axes, previous = {}, "document.source"
    for axis in ("extraction", "structure", "chunking", "enrichment", "embedding", "indexing"):
        axes[axis] = {"candidates": [{"plugin_id": "transform.synthetic@1", "configuration": {}, "inputs": {"source": previous}, "accept_quality": ["PASS", "WARN", "FAIL"]}]}
        previous = f"{axis}.result"
    value = {"schema_version": "v1", "default_profile_id": "default", "profiles": [{"profile_id": "default", "axes": axes}, {"profile_id": "pdf", "axes": axes}], "document_class_rules": [{"rule_id": "pdf-class", "document_class": "pdf", "profile_id": "pdf"}], "preflight_rules": [{"rule_id": "text", "when": {"eq": ["document.extension", "txt"]}, "profile_id": "pdf"}]}
    return json.dumps(value)


def test_resolver_precedence_and_recorded_evidence() -> None:
    compiled = ProfileCompiler(bootstrap_registry()).compile(ProfileParser.parse(source(), "application/json"))
    resolver = ProfileResolver()
    explicit = resolver.resolve(compiled, ResolutionRequest(explicit_profile_id="default", document_class="pdf"))
    classified = resolver.resolve(compiled, ResolutionRequest(document_class="pdf", extension="txt"))
    preflight = resolver.resolve(compiled, ResolutionRequest(extension="txt"))
    default = resolver.resolve(compiled, ResolutionRequest(extension="md"))
    assert (explicit.selection_tier, classified.selection_tier, preflight.selection_tier, default.selection_tier) == ("explicit", "document_class", "preflight", "default")
    assert classified.evaluated_rules[0] == {"rule_id": "pdf-class", "tier": "document_class", "matched": True}
    assert preflight.evaluated_rules[-1]["matched"] and "extension" in default.observables


def test_empty_explicit_profile_id_is_never_treated_as_unspecified() -> None:
    compiled = ProfileCompiler(bootstrap_registry()).compile(ProfileParser.parse(source(), "application/json"))
    with pytest.raises(ProfileError) as raised:
        ProfileResolver().resolve(compiled, ResolutionRequest(explicit_profile_id=""))
    assert raised.value.code is ProfileErrorCode.SELECTION_INVALID
    assert raised.value.location == "/explicit_profile_id"
