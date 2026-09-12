from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .compiler import CompiledQueryProfileSet, ResolvedQueryPlan, evaluate_condition
from .contracts import QueryArtifactBinding, QueryResolutionRequest
from .errors import QueryProfileError, QueryProfileErrorCode


@dataclass(frozen=True)
class QueryResolutionRecord:
    evaluated_rules: tuple[Any, ...]
    observables: Any
    selected_profile_id: str
    selection_tier: str
    plan: ResolvedQueryPlan
    search_artifact: QueryArtifactBinding


class QueryProfileResolver:
    def resolve(self, compiled: CompiledQueryProfileSet, request: QueryResolutionRequest) -> QueryResolutionRecord:
        rules: list[dict[str, Any]] = []
        if request.explicit_profile_id is not None:
            if not request.explicit_profile_id:
                raise QueryProfileError(QueryProfileErrorCode.SELECTION_INVALID, "/explicit_profile_id")
            return self._record(compiled, request, rules, compiled.get(request.explicit_profile_id), "explicit")
        observables = request.observables()
        class_matches = []
        conditional_matches = []
        for rule in compiled.profile_set.selection_rules:
            class_match = ((rule.question_class is None or rule.question_class == request.question_class) and (rule.document_class is None or rule.document_class == request.document_class))
            matched = class_match and (rule.when is None or evaluate_condition(rule.when, observables))
            tier = "class" if rule.when is None else "conditional"
            rules.append({"rule_id": rule.rule_id, "tier": tier, "matched": matched})
            if matched:
                (class_matches if rule.when is None else conditional_matches).append(rule)
        if len(class_matches) > 1:
            raise QueryProfileError(QueryProfileErrorCode.SELECTION_INVALID, "/selection_rules")
        if class_matches:
            return self._record(compiled, request, rules, compiled.get(class_matches[0].profile_id), "class")
        if len(conditional_matches) > 1:
            raise QueryProfileError(QueryProfileErrorCode.SELECTION_INVALID, "/selection_rules")
        if conditional_matches:
            return self._record(compiled, request, rules, compiled.get(conditional_matches[0].profile_id), "conditional")
        return self._record(compiled, request, rules, compiled.get(compiled.profile_set.default_profile_id), "default")

    @staticmethod
    def _record(compiled: CompiledQueryProfileSet, request: QueryResolutionRequest, rules: list[dict[str, Any]], plan: ResolvedQueryPlan, tier: str) -> QueryResolutionRecord:
        return QueryResolutionRecord(tuple(_freeze(rule) for rule in rules), _freeze(request.observables()), plan.profile_id, tier, plan, compiled.search_artifact)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value
