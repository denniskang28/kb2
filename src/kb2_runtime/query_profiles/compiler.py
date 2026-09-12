from __future__ import annotations

import json
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from kb2_runtime.plugins.errors import PluginError
from kb2_runtime.plugins.registry import PluginRegistry
from kb2_runtime.trace.service import plan_digest

from .contracts import QueryArtifactBinding, QueryProfile, QueryProfileSet, QueryStage, STAGE_KINDS
from .errors import QueryProfileError, QueryProfileErrorCode

_OBSERVABLES = {"question_class", "document_class", "language_hint", "question_length", "has_tables", "has_hierarchy"}


@dataclass(frozen=True)
class ResolvedQueryPlan:
    profile_id: str
    _canonical_payload: str
    digest: str

    @property
    def canonical_payload(self) -> dict[str, Any]:
        return json.loads(self._canonical_payload)


@dataclass(frozen=True)
class CompiledQueryProfileSet:
    profile_set: QueryProfileSet
    search_artifact: QueryArtifactBinding
    plans: dict[str, ResolvedQueryPlan]

    def get(self, profile_id: str) -> ResolvedQueryPlan:
        try:
            return self.plans[profile_id]
        except KeyError:
            raise QueryProfileError(QueryProfileErrorCode.SELECTION_INVALID, "/explicit_profile_id") from None


class QueryProfileCompiler:
    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry

    def compile(self, profile_set: QueryProfileSet, search_artifact: QueryArtifactBinding) -> CompiledQueryProfileSet:
        if not isinstance(search_artifact, QueryArtifactBinding):
            raise QueryProfileError(QueryProfileErrorCode.SCHEMA_INCOMPATIBLE, "/search_artifact")
        for index, rule in enumerate(profile_set.selection_rules):
            if rule.when is not None:
                self._validate_condition(rule.when, set(), f"/selection_rules/{index}/when")
        self._validate_rules(profile_set)
        plans = {profile.profile_id: self._compile_profile(profile, search_artifact) for profile in profile_set.profiles}
        return CompiledQueryProfileSet(profile_set, search_artifact, MappingProxyType(plans))

    def _compile_profile(self, profile: QueryProfile, artifact: QueryArtifactBinding) -> ResolvedQueryPlan:
        self._validate_order(profile)
        available: dict[str, tuple[str, str]] = {"query.question": ("opaque.bytes", "v1"), "search.index": (artifact.artifact_type, artifact.schema_revision)}
        quality: set[str] = set()
        stages: list[dict[str, Any]] = []
        for index, stage in enumerate(profile.stages):
            location = f"/profiles/{profile.profile_id}/stages/{index}"
            if stage.kind == "repair":
                if stage.max_attempts is None or not 1 <= stage.max_attempts <= 3:
                    raise QueryProfileError(QueryProfileErrorCode.REPAIR_UNBOUNDED, location + "/max_attempts")
                if not any(item["kind"] == "verify" for item in stages):
                    raise QueryProfileError(QueryProfileErrorCode.STAGE_ORDER_INVALID, location)
            elif stage.max_attempts is not None:
                raise QueryProfileError(QueryProfileErrorCode.REPAIR_UNBOUNDED, location + "/max_attempts")
            registration = self._registration(stage.plugin_id, location)
            descriptor = registration.descriptor
            try:
                configuration = registration.configuration_model.model_validate(stage.configuration).model_dump(mode="json")
            except ValidationError:
                raise QueryProfileError(QueryProfileErrorCode.CONFIGURATION_INVALID, location + "/configuration") from None
            inputs = self._inputs(stage, descriptor.input_ports, available, location)
            if stage.kind == "repair":
                self._validate_repair_inputs(inputs, stages, location)
            outputs = tuple(stage.outputs) or tuple(port.name for port in descriptor.output_ports)
            if len(outputs) != len(set(outputs)) or set(outputs) != {port.name for port in descriptor.output_ports}:
                raise QueryProfileError(QueryProfileErrorCode.PORT_UNBOUND, location + "/outputs")
            self._validate_condition(stage.when, quality, location + "/when")
            resolved_outputs = [{"name": port.name, "artifact_type": port.artifact_type, "schema_revision": port.schema_revision} for port in descriptor.output_ports if port.name in outputs]
            for output in resolved_outputs:
                key = f"{stage.stage_id}.{output['name']}"
                if key in available:
                    raise QueryProfileError(QueryProfileErrorCode.GRAPH_CYCLE, location)
                available[key] = (output["artifact_type"], output["schema_revision"])
            quality.update(f"quality.{stage.stage_id}.{name}" for name in descriptor.quality_signal_names)
            stages.append({"stage_id": stage.stage_id, "kind": stage.kind, "plugin_id": descriptor.plugin_id, "implementation_digest": descriptor.implementation_digest, "runner": descriptor.runner.value, "configuration": configuration, "inputs": inputs, "outputs": resolved_outputs, "when": stage.when, "max_attempts": stage.max_attempts})
        self._validate_final(stages)
        payload = {"schema_version": "v1", "profile_id": profile.profile_id, "search_artifact": artifact.model_dump(mode="json"), "stages": stages}
        try:
            digest = plan_digest(payload)
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        except Exception:
            raise QueryProfileError(QueryProfileErrorCode.PARSE_INVALID, f"/profiles/{profile.profile_id}") from None
        return ResolvedQueryPlan(profile.profile_id, canonical, digest)

    @staticmethod
    def _validate_order(profile: QueryProfile) -> None:
        kinds = [stage.kind for stage in profile.stages]
        order = {kind: index for index, kind in enumerate(STAGE_KINDS)}
        invalid = (any(left != "retrieve" and left in kinds[index + 1:] for index, left in enumerate(kinds))
                   or any(order[kinds[index]] > order[kinds[index + 1]] for index in range(len(kinds) - 1))
                   or kinds.count("retrieve") > 8 or "context" not in kinds or "final_state" not in kinds
                   or ("generate" in kinds and "verify" not in kinds))
        if invalid:
            raise QueryProfileError(QueryProfileErrorCode.STAGE_ORDER_INVALID, f"/profiles/{profile.profile_id}/stages")

    def _registration(self, plugin_id: str, location: str) -> Any:
        try:
            registration = self.registry.get(plugin_id)
        except PluginError:
            raise QueryProfileError(QueryProfileErrorCode.PLUGIN_UNKNOWN, location + "/plugin_id") from None
        if not self.registry.inspect(plugin_id)[0].runnable:
            raise QueryProfileError(QueryProfileErrorCode.PLUGIN_UNAVAILABLE, location + "/plugin_id")
        return registration

    @staticmethod
    def _inputs(stage: QueryStage, ports: Any, available: dict[str, tuple[str, str]], location: str) -> list[dict[str, Any]]:
        if set(stage.inputs) != {port.name for port in ports}:
            raise QueryProfileError(QueryProfileErrorCode.PORT_UNBOUND, location + "/inputs")
        result = []
        for port in ports:
            raw_source = stage.inputs[port.name]
            sources = raw_source if isinstance(raw_source, tuple) else (raw_source,)
            if not port.min_items <= len(sources) <= port.max_items or len(set(sources)) != len(sources):
                raise QueryProfileError(QueryProfileErrorCode.PORT_UNBOUND, location + f"/inputs/{port.name}")
            for source in sources:
                if source not in available:
                    code = QueryProfileErrorCode.GRAPH_CYCLE if "." in source and source not in {"query.question", "search.index"} else QueryProfileErrorCode.PORT_UNBOUND
                    raise QueryProfileError(code, location + f"/inputs/{port.name}")
                if available[source] != (port.artifact_type, port.schema_revision):
                    raise QueryProfileError(QueryProfileErrorCode.SCHEMA_INCOMPATIBLE, location + f"/inputs/{port.name}")
            result.append({"name": port.name, "source": sources[0] if len(sources) == 1 else list(sources), "artifact_type": port.artifact_type, "schema_revision": port.schema_revision})
        return result

    @staticmethod
    def _validate_final(stages: list[dict[str, Any]]) -> None:
        context = next(item for item in stages if item["kind"] == "context")
        if "evidence" not in {item["name"] for item in context["outputs"]}:
            raise QueryProfileError(QueryProfileErrorCode.FINAL_VALIDATION_MISSING, "/stages")
        final = next(item for item in stages if item["kind"] == "final_state")
        upstream = {
            f"{stage['stage_id']}.{output['name']}": {source for item in stage["inputs"] for source in (item["source"] if isinstance(item["source"], list) else [item["source"]])}
            for stage in stages for output in stage["outputs"]
        }
        evidence = f"{context['stage_id']}.evidence"

        def derives_from_evidence(source: str, seen: set[str] | None = None) -> bool:
            if source == evidence:
                return True
            if source not in upstream:
                return False
            seen = seen or set()
            return source not in seen and any(derives_from_evidence(item, seen | {source}) for item in upstream[source])

        if not any(derives_from_evidence(item["source"]) for item in final["inputs"]):
            raise QueryProfileError(QueryProfileErrorCode.FINAL_VALIDATION_MISSING, "/stages")

    @staticmethod
    def _validate_repair_inputs(inputs: list[dict[str, str]], stages: list[dict[str, Any]], location: str) -> None:
        evidence_sources = {
            f"{stage['stage_id']}.evidence"
            for stage in stages if stage["kind"] == "context"
        }
        generation_sources = {
            f"{stage['stage_id']}.{output['name']}"
            for stage in stages if stage["kind"] in {"generate", "verify"} for output in stage["outputs"]
        }
        allowed = evidence_sources | generation_sources
        for item in inputs:
            if item["source"] not in allowed:
                raise QueryProfileError(QueryProfileErrorCode.PORT_UNBOUND, location + f"/inputs/{item['name']}")

    @staticmethod
    def _validate_condition(node: Any, quality: set[str], location: str, depth: int = 0) -> None:
        if node is None:
            return
        if depth > 6 or not isinstance(node, dict) or len(node) != 1:
            raise QueryProfileError(QueryProfileErrorCode.CONDITION_UNSUPPORTED, location)
        op, value = next(iter(node.items()))
        if op in {"all", "any"}:
            if not isinstance(value, list) or not value or len(value) > 32:
                raise QueryProfileError(QueryProfileErrorCode.CONDITION_UNSUPPORTED, location)
            for child in value:
                QueryProfileCompiler._validate_condition(child, quality, location, depth + 1)
            return
        if op == "not":
            QueryProfileCompiler._validate_condition(value, quality, location, depth + 1)
            return
        if op not in {"eq", "in", "gte", "lte"} or not isinstance(value, list) or len(value) != 2:
            raise QueryProfileError(QueryProfileErrorCode.CONDITION_UNSUPPORTED, location)
        reference = value[0].get("ref") if isinstance(value[0], dict) and set(value[0]) == {"ref"} else value[0]
        operand = value[1]
        if not isinstance(reference, str) or (reference not in _OBSERVABLES and reference not in quality) or not _safe_operand(operand, op):
            raise QueryProfileError(QueryProfileErrorCode.CONDITION_UNSUPPORTED, location)
        if op in {"gte", "lte"} and (isinstance(operand, bool) or not isinstance(operand, (int, float)) or not math.isfinite(operand)):
            raise QueryProfileError(QueryProfileErrorCode.CONDITION_UNSUPPORTED, location)

    @staticmethod
    def _validate_rules(profile_set: QueryProfileSet) -> None:
        class_rules = [(index, rule) for index, rule in enumerate(profile_set.selection_rules) if rule.when is None]
        conditional_rules = [(index, rule) for index, rule in enumerate(profile_set.selection_rules) if rule.when is not None]
        for rules in (class_rules, conditional_rules):
            for first_offset, (first_index, first) in enumerate(rules):
                for _, second in rules[first_offset + 1:]:
                    if _selectors_overlap(first.question_class, second.question_class) and _selectors_overlap(first.document_class, second.document_class) and not _conditions_provably_disjoint(first.when, second.when):
                        raise QueryProfileError(QueryProfileErrorCode.SELECTION_INVALID, f"/selection_rules/{first_index}")


def _safe_operand(value: Any, op: str) -> bool:
    values = value if op == "in" and isinstance(value, list) else [value]
    return bool(values) and all(isinstance(item, (str, int, float, bool, type(None))) and not (isinstance(item, float) and not math.isfinite(item)) for item in values)


def _selectors_overlap(first: str | None, second: str | None) -> bool:
    return first is None or second is None or first == second


def _conditions_provably_disjoint(first: dict[str, Any] | None, second: dict[str, Any] | None) -> bool:
    """Only accept two rules together when their bounded predicates prove separation."""
    if first is None or second is None:
        return False
    first_constraint = _equality_constraint(first)
    second_constraint = _equality_constraint(second)
    return (first_constraint is not None and second_constraint is not None
            and first_constraint[0] == second_constraint[0]
            and first_constraint[1].isdisjoint(second_constraint[1]))


def _equality_constraint(condition: dict[str, Any]) -> tuple[str, set[Any]] | None:
    if len(condition) != 1:
        return None
    op, value = next(iter(condition.items()))
    if op not in {"eq", "in"} or not isinstance(value, list) or len(value) != 2:
        return None
    reference = value[0].get("ref") if isinstance(value[0], dict) and set(value[0]) == {"ref"} else value[0]
    values = value[1] if op == "in" and isinstance(value[1], list) else [value[1]]
    if not isinstance(reference, str) or not _safe_operand(values, "in"):
        return None
    return reference, set(values)


def evaluate_condition(condition: dict[str, Any] | None, observables: dict[str, Any]) -> bool:
    if condition is None:
        return True
    op, value = next(iter(condition.items()))
    if op == "all": return all(evaluate_condition(item, observables) for item in value)
    if op == "any": return any(evaluate_condition(item, observables) for item in value)
    if op == "not": return not evaluate_condition(value, observables)
    reference = value[0].get("ref") if isinstance(value[0], dict) else value[0]
    actual, expected = observables.get(reference), value[1]
    if op == "eq": return actual == expected
    if op == "in": return actual in expected
    if op == "gte": return isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual >= expected
    return isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual <= expected
