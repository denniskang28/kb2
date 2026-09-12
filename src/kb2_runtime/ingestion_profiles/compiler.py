from __future__ import annotations

import json
import itertools
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from kb2_runtime.plugins.errors import PluginError, PluginErrorCode
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.trace.service import plan_digest

from .contracts import AXES, Candidate, ProfileSet, QualityResult
from .errors import ProfileError, ProfileErrorCode


@dataclass(frozen=True)
class ResolvedPlan:
    profile_id: str
    _canonical_payload: str
    digest: str

    @property
    def canonical_payload(self) -> dict[str, Any]:
        """A fresh JSON-safe snapshot suitable for S-002 plan persistence."""
        return json.loads(self._canonical_payload)


@dataclass(frozen=True)
class CompiledProfileSet:
    profile_set: ProfileSet
    plans: dict[str, ResolvedPlan]

    def get(self, profile_id: str) -> ResolvedPlan:
        try:
            return self.plans[profile_id]
        except KeyError:
            raise ProfileError(ProfileErrorCode.SELECTION_INVALID, "/explicit_profile_id") from None


class ProfileCompiler:
    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry

    def compile(self, profile_set: ProfileSet) -> CompiledProfileSet:
        for index, rule in enumerate(profile_set.preflight_rules):
            self._validate_condition(rule.when, "", "", [], {}, f"/preflight_rules/{index}/when")
        self._reject_ambiguous_preflight_rules(profile_set)
        plans = {profile.profile_id: self._compile_profile(profile_set, profile) for profile in profile_set.profiles}
        return CompiledProfileSet(profile_set=profile_set, plans=MappingProxyType(plans))

    def _compile_profile(self, profile_set: ProfileSet, profile: Any) -> ResolvedPlan:
        available: dict[str, tuple[str, str]] = {
            f"document.{name}": schema.pair for name, schema in profile_set.document_inputs.items()
        }
        quality_by_stage: dict[tuple[str, str], set[str]] = {}
        completed_sub_stages: list[tuple[str, str]] = []
        stages: list[dict[str, Any]] = []
        for axis_index, axis_name in enumerate(AXES):
            axis = profile.axes[axis_name]
            resolved_sub_stages: list[dict[str, Any]] = []
            for sub_index, sub_stage in enumerate(axis.normalized_sub_stages):
                base = "sub_stages" if axis.sub_stages is not None else "candidates"
                location = f"/profiles/{profile.profile_id}/axes/{axis_name}/{base}/{sub_index}"
                candidates = self._compile_candidates(
                    sub_stage.candidates, available, axis_name, sub_stage.stage_id,
                    completed_sub_stages, quality_by_stage, location,
                )
                first_outputs = {(output["name"], output["artifact_type"], output["schema_revision"]) for output in candidates[0]["outputs"]}
                if any({(output["name"], output["artifact_type"], output["schema_revision"]) for output in item["outputs"]} != first_outputs for item in candidates[1:]):
                    raise ProfileError(ProfileErrorCode.SCHEMA_INCOMPATIBLE, location)
                for name, artifact_type, revision in first_outputs:
                    key = f"{axis_name}.{sub_stage.stage_id}.{name}"
                    if key in available:
                        raise ProfileError(ProfileErrorCode.GRAPH_CYCLE, location)
                    available[key] = (artifact_type, revision)
                    if axis.sub_stages is None:
                        available[f"{axis_name}.{name}"] = (artifact_type, revision)
                quality_by_stage[(axis_name, sub_stage.stage_id)] = {
                    signal for item in candidates for signal in self._registration(item["plugin_id"], "/").descriptor.quality_signal_names
                }
                completed_sub_stages.append((axis_name, sub_stage.stage_id))
                resolved_sub_stages.append({"stage_id": sub_stage.stage_id, "candidates": candidates, "on_exhausted": sub_stage.on_exhausted})
            resolved_axis = {"axis": axis_name, "sub_stages": resolved_sub_stages}
            # Keep the prior read-only lookup shape for legacy source Profiles;
            # execution and all new plans use the explicit sub_stages payload.
            if axis.sub_stages is None:
                resolved_axis["legacy_alias"] = True
                resolved_axis["candidates"] = resolved_sub_stages[0]["candidates"]
                resolved_axis["on_exhausted"] = resolved_sub_stages[0]["on_exhausted"]
            stages.append(resolved_axis)
        payload = {
            "schema_version": "v1",
            "profile_id": profile.profile_id,
            "document_inputs": {
                name: {"artifact_type": schema.artifact_type, "schema_revision": schema.schema_revision}
                for name, schema in profile_set.document_inputs.items()
            },
            "stages": stages,
        }
        try:
            digest = plan_digest(payload)
        except Exception:
            raise ProfileError(ProfileErrorCode.PARSE_INVALID, f"/profiles/{profile.profile_id}") from None
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        return ResolvedPlan(profile.profile_id, canonical, digest)

    def _compile_candidates(self, source_candidates: tuple[Candidate, ...], available: dict[str, tuple[str, str]], axis_name: str, stage_id: str, completed_sub_stages: list[tuple[str, str]], quality_by_stage: dict[tuple[str, str], set[str]], location: str) -> list[dict[str, Any]]:
        candidates = []
        for candidate_index, candidate in enumerate(source_candidates):
            candidate_location = f"{location}/candidates/{candidate_index}"
            registration = self._registration(candidate.plugin_id, candidate_location)
            descriptor = registration.descriptor
            try:
                configuration = registration.configuration_model.model_validate(candidate.configuration).model_dump(mode="json")
            except ValidationError:
                raise ProfileError(ProfileErrorCode.CONFIGURATION_INVALID, candidate_location + "/configuration") from None
            inputs = self._inputs(candidate, descriptor.input_ports, available, candidate_location)
            outputs = tuple(candidate.outputs) or tuple(port.name for port in descriptor.output_ports)
            if len(set(outputs)) != len(outputs) or set(outputs) != {port.name for port in descriptor.output_ports}:
                raise ProfileError(ProfileErrorCode.PORT_UNBOUND, candidate_location + "/outputs")
            self._validate_condition(candidate.when, axis_name, stage_id, completed_sub_stages, quality_by_stage, candidate_location + "/when")
            candidates.append({"plugin_id": descriptor.plugin_id, "implementation_digest": descriptor.implementation_digest,
                "runner": descriptor.runner.value, "configuration": configuration, "inputs": inputs,
                "outputs": [{"name": port.name, "artifact_type": port.artifact_type, "schema_revision": port.schema_revision}
                            for port in descriptor.output_ports if port.name in outputs], "when": candidate.when,
                "accept_quality": [item.value for item in candidate.accept_quality]})
        return candidates

    def _registration(self, plugin_id: str, location: str) -> Any:
        try:
            registration = self.registry.get(plugin_id)
        except PluginError as exc:
            if exc.code is PluginErrorCode.NOT_REGISTERED:
                raise ProfileError(ProfileErrorCode.PLUGIN_UNKNOWN, location + "/plugin_id") from None
            raise ProfileError(ProfileErrorCode.PLUGIN_UNKNOWN, location + "/plugin_id") from None
        if not self.registry.inspect(plugin_id)[0].runnable:
            raise ProfileError(ProfileErrorCode.PLUGIN_UNAVAILABLE, location + "/plugin_id")
        return registration

    @staticmethod
    def _inputs(candidate: Candidate, ports: Any, available: dict[str, tuple[str, str]], location: str) -> list[dict[str, str]]:
        expected = {port.name: port for port in ports}
        if set(candidate.inputs) != set(expected):
            raise ProfileError(ProfileErrorCode.PORT_UNBOUND, location + "/inputs")
        resolved = []
        for port in ports:
            name, source = port.name, candidate.inputs[port.name]
            if source not in available:
                code = ProfileErrorCode.GRAPH_CYCLE if source.split(".", 1)[0] in AXES else ProfileErrorCode.PORT_UNBOUND
                raise ProfileError(code, location + f"/inputs/{name}")
            if available[source] != (port.artifact_type, port.schema_revision):
                raise ProfileError(ProfileErrorCode.SCHEMA_INCOMPATIBLE, location + f"/inputs/{name}")
            resolved.append({"name": name, "source": source, "artifact_type": port.artifact_type, "schema_revision": port.schema_revision})
        return resolved

    def _validate_condition(self, condition: dict[str, Any] | None, axis_name: str, stage_id: str, completed_sub_stages: list[tuple[str, str]], quality_by_stage: dict[tuple[str, str], set[str]], location: str) -> None:
        if condition is None:
            return
        try:
            self._condition(condition, axis_name, stage_id, completed_sub_stages, quality_by_stage, 0)
        except ProfileError as exc:
            raise ProfileError(exc.code, location) from None

    def _condition(self, node: Any, axis_name: str, stage_id: str, completed_sub_stages: list[tuple[str, str]], quality_by_stage: dict[tuple[str, str], set[str]], depth: int) -> None:
        if depth > 6 or not isinstance(node, dict) or len(node) != 1:
            raise ProfileError(ProfileErrorCode.CONDITION_UNSUPPORTED)
        op, value = next(iter(node.items()))
        if op in {"all", "any"}:
            if not isinstance(value, list) or not value or len(value) > 32:
                raise ProfileError(ProfileErrorCode.CONDITION_UNSUPPORTED)
            for item in value:
                self._condition(item, axis_name, stage_id, completed_sub_stages, quality_by_stage, depth + 1)
        elif op == "not":
            self._condition(value, axis_name, stage_id, completed_sub_stages, quality_by_stage, depth + 1)
        elif op in {"eq", "in", "gte", "lte"}:
            if not isinstance(value, list) or len(value) != 2:
                raise ProfileError(ProfileErrorCode.CONDITION_UNSUPPORTED)
            reference = _reference(value[0])
            if reference is None or not _valid_reference(reference, completed_sub_stages, quality_by_stage):
                raise ProfileError(ProfileErrorCode.CONDITION_UNSUPPORTED)
            if not _safe_operand(value[1], op):
                raise ProfileError(ProfileErrorCode.CONDITION_UNSUPPORTED) from None
            if op in {"gte", "lte"} and not _ordered_operand(reference, value[1]):
                raise ProfileError(ProfileErrorCode.CONDITION_UNSUPPORTED)
        else:
            raise ProfileError(ProfileErrorCode.CONDITION_UNSUPPORTED)

    def _reject_ambiguous_preflight_rules(self, profile_set: ProfileSet) -> None:
        rules = profile_set.preflight_rules
        for first_index, first in enumerate(rules):
            for second in rules[first_index + 1:]:
                if _conditions_overlap(first.when, second.when):
                    raise ProfileError(ProfileErrorCode.SELECTION_INVALID, f"/preflight_rules/{first_index}")


def _reference(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and set(value) == {"ref"} and isinstance(value["ref"], str):
        return value["ref"]
    return None


def _valid_reference(reference: str, completed_sub_stages: list[tuple[str, str]], quality_by_stage: dict[tuple[str, str], set[str]]) -> bool:
    document = {"document.media_type", "document.extension", "document.byte_size", "document.page_count", "document.language_hint", "document.has_embedded_text", "document.is_scanned", "document.document_class"}
    if reference in document:
        return True
    parts = reference.split(".")
    if len(parts) == 3 and parts[0] == "quality":
        matches = [key for key in completed_sub_stages if key[0] == parts[1]]
        return len(matches) == 1 and parts[2] in quality_by_stage.get(matches[0], set())
    return len(parts) == 4 and parts[0] == "quality" and (parts[1], parts[2]) in completed_sub_stages and parts[3] in quality_by_stage.get((parts[1], parts[2]), set())


_DOCUMENT_DEFAULTS: dict[str, Any] = {
    "document.media_type": "", "document.extension": "", "document.byte_size": 0,
    "document.page_count": 0, "document.language_hint": "", "document.has_embedded_text": False,
    "document.is_scanned": False, "document.document_class": None,
}


def _ordered_operand(reference: str, value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if reference in {"document.byte_size", "document.page_count"}:
        return isinstance(value, int)
    # Quality signal values are declared JSON primitives, so ordered checks are numeric only.
    return reference.startswith("quality.") and isinstance(value, (int, float)) and math.isfinite(value)


def _safe_operand(value: Any, op: str) -> bool:
    values = value if op == "in" and isinstance(value, list) else [value]
    return bool(values) and all(
        isinstance(item, (str, int, float, bool, type(None)))
        and not (isinstance(item, float) and not math.isfinite(item))
        for item in values
    )


def _condition_references(node: Any) -> set[str]:
    if not isinstance(node, dict) or len(node) != 1:
        return set()
    op, value = next(iter(node.items()))
    if op in {"all", "any"}:
        return set().union(*(_condition_references(item) for item in value))
    if op == "not":
        return _condition_references(value)
    reference = _reference(value[0]) if isinstance(value, list) and value else None
    return {reference} if reference else set()


def _condition_literals(node: Any, reference: str) -> set[Any]:
    if not isinstance(node, dict) or len(node) != 1:
        return set()
    op, value = next(iter(node.items()))
    if op in {"all", "any"}:
        return set().union(*(_condition_literals(item, reference) for item in value))
    if op == "not" or not isinstance(value, list) or len(value) != 2 or _reference(value[0]) != reference:
        return set()
    if op == "in" and isinstance(value[1], list):
        return set(value[1])
    return {value[1]}


def _conditions_overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    references = _condition_references(first) | _condition_references(second)
    domains: list[tuple[str, tuple[Any, ...]]] = []
    for reference in sorted(references):
        values = {_DOCUMENT_DEFAULTS[reference]}
        for literal in _condition_literals(first, reference) | _condition_literals(second, reference):
            if isinstance(literal, (str, int, bool, type(None))) or (isinstance(literal, float) and math.isfinite(literal)):
                values.add(literal)
                if isinstance(literal, (int, float)) and not isinstance(literal, bool):
                    values.update({literal - 1, literal + 1})
        domains.append((reference, tuple(values)))
    combinations = 1
    for _, values in domains:
        combinations *= len(values)
    if combinations > 65536:
        # A compile-time guarantee cannot rely on resolver ordering when the
        # bounded declarative analysis cannot prove these rules disjoint.
        return True
    for values in itertools.product(*(values for _, values in domains)):
        document = {**{key.split(".", 1)[1]: value for key, value in _DOCUMENT_DEFAULTS.items()}, **{
            reference.split(".", 1)[1]: value for (reference, _), value in zip(domains, values, strict=True)
        }}
        if evaluate_condition(first, document) and evaluate_condition(second, document):
            return True
    return False


def evaluate_condition(condition: dict[str, Any] | None, document: dict[str, Any], quality: dict[str, Any] | None = None) -> bool:
    if condition is None:
        return True
    op, value = next(iter(condition.items()))
    if op == "all": return all(evaluate_condition(item, document, quality) for item in value)
    if op == "any": return any(evaluate_condition(item, document, quality) for item in value)
    if op == "not": return not evaluate_condition(value, document, quality)
    reference = _reference(value[0])
    actual = document.get(reference.split(".", 1)[1]) if reference and reference.startswith("document.") else (quality or {}).get(reference or "")
    expected = value[1]
    if op == "eq": return actual == expected
    if op == "in": return actual in expected if isinstance(expected, list) else False
    if op == "gte": return isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual >= expected
    return isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual <= expected
