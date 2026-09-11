from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .compiler import CompiledProfileSet, ResolvedPlan, evaluate_condition
from .contracts import ResolutionRequest
from .errors import ProfileError, ProfileErrorCode


@dataclass(frozen=True)
class ResolutionRecord:
    candidate_profile_ids: tuple[str, ...]
    evaluated_rules: tuple[dict[str, Any], ...]
    observables: dict[str, Any]
    selected_profile_id: str
    selection_tier: str
    plan: ResolvedPlan


class ProfileResolver:
    def resolve(self, compiled: CompiledProfileSet, request: ResolutionRequest) -> ResolutionRecord:
        rules: list[dict[str, Any]] = []
        if request.explicit_profile_id is not None:
            if not request.explicit_profile_id:
                raise ProfileError(ProfileErrorCode.SELECTION_INVALID, "/explicit_profile_id")
            plan = compiled.get(request.explicit_profile_id)
            return self._record(compiled, request, rules, plan, "explicit")
        class_matches = []
        for rule in compiled.profile_set.document_class_rules:
            matched = request.document_class == rule.document_class
            rules.append({"rule_id": rule.rule_id, "tier": "document_class", "matched": matched})
            if matched: class_matches.append(rule)
        if len(class_matches) > 1:
            raise ProfileError(ProfileErrorCode.SELECTION_INVALID, "/document_class_rules")
        if class_matches:
            return self._record(compiled, request, rules, compiled.get(class_matches[0].profile_id), "document_class")
        preflight_matches = []
        document = request.observables()
        for rule in compiled.profile_set.preflight_rules:
            matched = evaluate_condition(rule.when, document)
            rules.append({"rule_id": rule.rule_id, "tier": "preflight", "matched": matched})
            if matched: preflight_matches.append(rule)
        if len(preflight_matches) > 1:
            raise ProfileError(ProfileErrorCode.SELECTION_INVALID, "/preflight_rules")
        if preflight_matches:
            return self._record(compiled, request, rules, compiled.get(preflight_matches[0].profile_id), "preflight")
        return self._record(compiled, request, rules, compiled.get(compiled.profile_set.default_profile_id), "default")

    @staticmethod
    def _record(compiled: CompiledProfileSet, request: ResolutionRequest, rules: list[dict[str, Any]], plan: ResolvedPlan, tier: str) -> ResolutionRecord:
        return ResolutionRecord(tuple(compiled.plans), tuple(rules), request.observables(), plan.profile_id, tier, plan)
