from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from kb2_runtime.evaluation.datasets.contracts import DatasetContent, canonical_bytes
from kb2_runtime.evaluation.datasets.service import DatasetService
from kb2_runtime.evaluation.ingestion.contracts import MetricMatch, MetricReport, MetricStatus, metric_report_bytes
from kb2_runtime.evidence.contracts import EvidenceSet
from kb2_runtime.generation.contracts import FinalResponse, GeneratedAnswer, VerificationResult
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput

from .contracts import AnswerMetricConfig, CITATION_METRICS, DECISION_METRICS, FACT_METRICS


def _normalized_with_positions(value: str) -> tuple[str, tuple[int, ...]]:
    parts: list[str] = []
    positions: list[int] = []
    pending_space = False
    for index, char in enumerate(value):
        normalized = unicodedata.normalize("NFKC", char).casefold()
        for item in normalized:
            if item.isspace():
                pending_space = bool(parts)
            else:
                if pending_space:
                    parts.append(" "); positions.append(index); pending_space = False
                parts.append(item); positions.append(index)
    return "".join(parts), tuple(positions)


def _fact_matches(answer: str, fact: str) -> tuple[tuple[int, int], ...]:
    normalized_answer, positions = _normalized_with_positions(answer)
    normalized_fact, _ = _normalized_with_positions(fact)
    if not normalized_fact:
        return ()
    expression = re.escape(normalized_fact).replace(r"\ ", r"\s+")
    return tuple((positions[item.start()], positions[item.end() - 1] + 1) for item in re.finditer(expression, normalized_answer))


def _locator_fingerprint(item: object) -> str:
    locators = [locator.model_dump(mode="json") for locator in item.locators]
    return hashlib.sha256(json.dumps(locators, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def _cohort_digest(cohort: tuple[str, ...]) -> str | None:
    if not cohort:
        return None
    return hashlib.sha256(json.dumps(sorted(cohort), separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def _answer_with_raw_citations(raw: bytes) -> tuple[GeneratedAnswer, tuple[object, ...]]:
    """Retain bounded malformed citation evidence without relaxing generation output validation."""
    payload = json.loads(raw)
    citations = payload.get("citation_keys")
    if not isinstance(citations, list) or len(citations) > 100:
        raise ValueError("generated answer citation inventory is invalid")
    raw_citations = tuple(citations)
    safe: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(raw_citations):
        if isinstance(value, str) and re.fullmatch(r"cit_[a-f0-9]{32}", value) and value not in seen:
            safe.append(value); seen.add(value)
        else:
            safe.append("cit_" + hashlib.sha256(f"malformed:{index}".encode()).hexdigest()[:32])
    payload["citation_keys"] = safe or ["cit_" + "0" * 32]
    return GeneratedAnswer.model_validate(payload), raw_citations


class AnswerMetricPlugin:
    def __init__(self, metric_id: str) -> None:
        self.metric_id = metric_id

    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        config = AnswerMetricConfig.model_validate(context.invocation.validated_configuration)
        inputs = [await context.input(item.id) for item in context.invocation.inputs]
        try:
            raw = json.loads(inputs[0].content)
            content = DatasetContent.model_validate({"taxonomy": raw["taxonomy"], "annotations": raw.get("annotations", []), "query_cases": raw.get("query_cases", [])})
            evidence = EvidenceSet.model_validate_json(inputs[1].content)
            response = FinalResponse.model_validate_json(inputs[-1].content)
        except Exception as exc:
            raise ValueError("answer metric inputs are invalid") from exc
        case = next((item for item in content.query_cases if item.id == config.case_id), None)
        if case is None or case.evidence is None or case.evidence.id != inputs[1].reference.id or case.evidence.content_digest != inputs[1].reference.content_digest:
            raise ValueError("reviewed case evidence binding is invalid")
        if (not DatasetService._is_reviewed(case)
                or case.source.artifact_type != "canonical.document"
                or any(set(item.slices) != set(content.taxonomy.dimensions)
                       or any(value not in content.taxonomy.dimensions[key] for key, value in item.slices.items())
                       for item in content.query_cases)):
            raise ValueError("snapshot review provenance or slices are invalid")
        if response.evidence_artifact_id != inputs[1].reference.id:
            raise ValueError("final response evidence binding is invalid")
        if self.metric_id in DECISION_METRICS:
            if config.cohort and (config.case_id not in config.cohort or len(config.cohort) != len(set(config.cohort))):
                raise ValueError("decision cohort binding is invalid")
            return self._decision(case, content, inputs[0].reference.id, inputs[1].reference.id, inputs[-1].reference.id, response, config.cohort)
        if len(inputs) != 5:
            raise ValueError("answer attempt metrics require generation bindings")
        answer, raw_citations = _answer_with_raw_citations(inputs[2].content)
        verification = VerificationResult.model_validate_json(inputs[3].content)
        if (answer.evidence_artifact_id != inputs[1].reference.id or answer.evidence_digest != inputs[1].reference.content_digest
                or verification.evidence_artifact_id != inputs[1].reference.id or verification.evidence_digest != inputs[1].reference.content_digest
                or verification.generated_answer_artifact_id != inputs[2].reference.id
                or response.generated_answer_artifact_id != inputs[2].reference.id
                or response.verification_artifact_id != inputs[3].reference.id):
            raise ValueError("answer metric cross-artifact binding is invalid")
        base = self._base(case, content, inputs[0].reference.id, inputs[1].reference.id, inputs[-1].reference.id,
                          answer_id=inputs[2].reference.id, verification_id=inputs[3].reference.id)
        if self.metric_id in FACT_METRICS:
            raw_labels = case.expected_facts if self.metric_id.endswith("expected-fact-coverage@1") else case.forbidden_facts
            labels = tuple(dict.fromkeys(_normalized_with_positions(label)[0] for label in raw_labels))
            if self.metric_id.endswith("expected-fact-coverage@1") and case.answerability != "answerable":
                return self._report(base, MetricStatus.NOT_APPLICABLE, None, 0, 0, ())
            if not labels:
                status = MetricStatus.INSUFFICIENT_LABELS if self.metric_id.endswith("expected-fact-coverage@1") else MetricStatus.NOT_APPLICABLE
                return self._report(base, status, None, 0, 0, ())
            matches = tuple(
                MetricMatch(source_id="fact:" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:32], relevant=bool(spans), span_start=start, span_end=end)
                for label in labels for start, end in _fact_matches(answer.answer, label)
            )
            matched = len({match.source_id for match in matches})
            return self._report(base, MetricStatus.VALUE, matched / len(labels), len(labels), matched, matches)
        if self.metric_id in CITATION_METRICS:
            return self._citations(base, case, evidence, answer, verification, raw_citations)
        raise ValueError("unknown answer metric")

    def _base(self, case, content, snapshot_id, evidence_id, final_id, answer_id=None, verification_id=None):
        return dict(metric_id=self.metric_id, metric_family_id=self.metric_id, owner=("answer" if self.metric_id in FACT_METRICS else "citation"), required_annotation_kinds=(), document_id=None,
                    snapshot_artifact_id=snapshot_id, expected_artifact_id=None, observed_artifact_id=None,
                    taxonomy_digest=hashlib.sha256(canonical_bytes(content.taxonomy)).hexdigest(), slices=case.slices,
                    elapsed_ms=0, case_id=case.id, question_source_artifact_id=case.source.id, label_evidence_artifact_id=evidence_id,
                    stage_kind="generation" if self.metric_id in FACT_METRICS else "verification", measured_artifact_id=None, k=None,
                    answer_artifact_id=answer_id, verification_artifact_id=verification_id, final_response_artifact_id=final_id,
                    direction="lower_is_better" if self.metric_id.endswith("forbidden-fact-violation@1") else "higher_is_better")

    @staticmethod
    def _report(base, status, value, labelled, matched, matches):
        report = MetricReport(**base, status=status, value=value, labelled_count=labelled, matched_count=matched, matches=matches, sample_count=labelled)
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="metric.report", schema_revision="v1", content=metric_report_bytes(report), summary="answer metric report"),), summary="answer metric report")

    def _citations(self, base, case, evidence, answer, verification, raw_citations=None):
        inventory = {item.citation_key: item for item in evidence.items}
        generated = tuple(answer.citation_keys if raw_citations is None else raw_citations)
        diagnostics = tuple(
            MetricMatch(source_id="citation:" + key, relevant=(key in inventory and key in verification.resolved_citation_keys and key not in verification.missing_citation_keys), citation_key=key,
                evidence_id=inventory[key].evidence_id if key in inventory else None, locator_fingerprint=_locator_fingerprint(inventory[key]) if key in inventory else None,
                decision_id="resolved" if key in verification.resolved_citation_keys else "unsupported")
            if isinstance(key, str) and re.fullmatch(r"cit_[a-f0-9]{32}", key)
            else MetricMatch(source_id="malformed-citation:" + hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:32], relevant=False, decision_id="malformed")
            for key in generated
        )
        if self.metric_id.endswith("precision@1"):
            if not case.required_citation_keys:
                return self._report(base, MetricStatus.INSUFFICIENT_LABELS, None, 0, 0, diagnostics)
            valid = sum(item.relevant for item in diagnostics)
            return self._report(base, MetricStatus.VALUE, valid / len(generated) if generated else 0.0, len(generated), valid, diagnostics)
        if not case.required_citation_keys:
            return self._report(base, MetricStatus.INSUFFICIENT_LABELS, None, 0, 0, diagnostics)
        required = set(case.required_citation_keys)
        valid = {item.citation_key for item in diagnostics if item.relevant and item.citation_key is not None}
        missing = tuple(MetricMatch(source_id="required-citation:" + key, relevant=False, citation_key=key, decision_id="missing") for key in sorted(required - valid))
        return self._report(base, MetricStatus.VALUE, len(valid & required) / len(required), len(required), len(valid & required), diagnostics + missing)

    def _decision(self, case, content, snapshot_id, evidence_id, final_id, response, cohort=()):
        family, measure = self.metric_id.removeprefix("metric.decision.").removesuffix("@1").rsplit("-", 1)
        expected, predicted = {
            "answerability": (case.answerability == "answerable", response.state == "ANSWERED"),
            "ambiguity": (case.answerability == "ambiguous", response.state == "CLARIFICATION_REQUIRED"),
            "abstention": (case.answerability == "unanswerable", response.state == "ABSTAINED"),
        }[family]
        outcome = "TP" if expected and predicted else "FP" if predicted else "FN" if expected else "TN"
        base = dict(metric_id=self.metric_id, metric_family_id="metric.decision." + family + "@1", owner="decision", required_annotation_kinds=(), document_id=None,
                    snapshot_artifact_id=snapshot_id, expected_artifact_id=None, observed_artifact_id=None, taxonomy_digest=hashlib.sha256(canonical_bytes(content.taxonomy)).hexdigest(), slices=case.slices,
                    elapsed_ms=0, case_id=case.id, question_source_artifact_id=None, label_evidence_artifact_id=evidence_id, stage_kind="final_state", measured_artifact_id=None, k=None,
                    answer_artifact_id=None, verification_artifact_id=None, final_response_artifact_id=final_id, cohort_digest=_cohort_digest(cohort), cohort_case_ids=tuple(sorted(cohort)))
        denominator = predicted if measure == "precision" else expected
        status = MetricStatus.VALUE if denominator else (MetricStatus.NOT_APPLICABLE if measure == "precision" else MetricStatus.INSUFFICIENT_LABELS)
        return self._report(base, status, 1.0 if expected and predicted else 0.0 if denominator else None, int(denominator), int(expected and predicted), (MetricMatch(source_id="decision:" + case.id, relevant=expected and predicted, decision_id=outcome),))
