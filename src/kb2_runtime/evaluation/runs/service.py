from __future__ import annotations

import resource
import time
from statistics import NormalDist
from dataclasses import dataclass
import hashlib
import json
from uuid import UUID

from kb2_runtime.evaluation.datasets.contracts import DatasetContent, canonical_bytes as dataset_bytes
from kb2_runtime.evaluation.datasets.service import DatasetService
from kb2_runtime.evaluation.metrics import MetricAggregator, MetricReport, MetricStatus, metric_aggregate_bytes
from kb2_runtime.trace.contracts import ArtifactInput, EngineKind
from kb2_runtime.trace.service import plan_digest
from .contracts import ArtifactBinding, ComparisonMode, Delta, EvaluationManifest, FailedCaseLink, GateResult, GateState, LayeredReport, NavigationIndex, OperationReport, QualityGate, ReplayObservation, SubjectMetricReport, canonical_bytes, digest


@dataclass(frozen=True)
class ComparisonResult:
    mode: ComparisonMode
    axis: str | None
    changes: tuple[str, ...]
    deltas: tuple[Delta, ...]
    recommendation: str


class EvaluationService:
    """Pure, fail-closed evaluation policy; persistence adapters own Artifact I/O."""
    @staticmethod
    def validate_manifest(manifest: EvaluationManifest, dataset_digest: str, reviewed_case_ids: tuple[str, ...], registered_metrics: tuple[str, ...], bindings: tuple[ArtifactBinding, ...]) -> None:
        if manifest.dataset_snapshot_digest != dataset_digest:
            raise ValueError("dataset snapshot digest mismatch")
        if set(manifest.case_ids) - set(reviewed_case_ids):
            raise ValueError("dataset contains unreviewed cases")
        if set(manifest.metric_ids) - set(registered_metrics):
            raise ValueError("metric is not registered")
        inventory = {(x.case_id, x.role, x.artifact_id, x.content_digest) for x in bindings}
        declared = {(x.case_id, x.role, x.artifact_id, x.content_digest) for subject in manifest.subjects for x in subject.bindings}
        if declared - inventory:
            raise ValueError("manifest input binding is missing from catalog")

    def __init__(self, metric_dispatcher: object | None = None, registered_metrics: tuple[str, ...] = ()) -> None:
        self.metric_dispatcher = metric_dispatcher
        self.registered_metrics = registered_metrics

    @staticmethod
    def catalog_levels(bindings: tuple[ArtifactBinding, ...], fanout: int = 64) -> tuple[tuple[tuple[ArtifactBinding, ...], ...], ...]:
        if not 1 <= fanout <= 64: raise ValueError("catalog fanout is invalid")
        ordered = tuple(sorted(bindings, key=lambda item: (item.case_id or "", item.role, str(item.artifact_id))))
        if len({(x.case_id, x.role) for x in ordered}) != len(ordered): raise ValueError("catalog has duplicate role binding")
        return (tuple(ordered[i:i + fanout] for i in range(0, len(ordered), fanout)),)

    @staticmethod
    def evaluate_gate(gate: QualityGate, reports: tuple[tuple[UUID, MetricReport], ...]) -> GateResult:
        selected = tuple((identifier, item) for identifier, item in reports if item.metric_id == gate.metric_id and item.owner == gate.owner and all(item.slices.get(k) == v for k, v in gate.selector.items()))
        ids = tuple(identifier for identifier, _ in selected)
        cases = tuple(sorted({item.case_id for _, item in selected if item.case_id}))
        if not selected: return GateResult(gate_id=gate.gate_id, state=GateState.INSUFFICIENT, reason="NO_SELECTED_REPORTS", selected_report_ids=ids, matched_case_ids=cases, sample_count=0)
        if gate.owner == "judge" and any(item.eligibility != "ELIGIBLE" for _, item in selected):
            return GateResult(gate_id=gate.gate_id, state=GateState.INELIGIBLE, reason="JUDGE_NOT_ELIGIBLE", selected_report_ids=ids, matched_case_ids=cases, sample_count=0)
        values = [item.value for _, item in selected if item.status is MetricStatus.VALUE]
        if len(values) < gate.minimum_samples or any(item.status is not MetricStatus.VALUE for _, item in selected):
            return GateResult(gate_id=gate.gate_id, state=GateState.INSUFFICIENT, reason="INSUFFICIENT_OR_MISSING_DATA", selected_report_ids=ids, matched_case_ids=cases, sample_count=len(values))
        if gate.aggregation == "any_failure":
            # Metric diagnostics are a closed vocabulary. Do not infer a gate
            # failure from arbitrary text embedded in a future diagnostic.
            failure_codes = {
                "unsupported_fact": frozenset({"unsupported", "unsupported_content"}),
                "invalid_citation": frozenset({"malformed", "missing", "unsupported"}),
            }[gate.failure_code]
            failed = any(any((match.decision_id or "").casefold() in failure_codes for match in item.matches) for _, item in selected)
            return GateResult(gate_id=gate.gate_id, state=GateState.FAIL if failed else GateState.PASS, reason="ANY_FAILURE" if failed else "NO_FAILURE", selected_report_ids=ids, matched_case_ids=cases, sample_count=len(values), value=0.0 if failed else 1.0)
        value = sum(values) / len(values)
        passes = value >= gate.threshold if gate.direction == "higher_is_better" else value <= gate.threshold
        return GateResult(gate_id=gate.gate_id, state=GateState.PASS if passes else GateState.FAIL, reason="THRESHOLD", selected_report_ids=ids, matched_case_ids=cases, sample_count=len(values), value=value)

    @staticmethod
    def operation(start_ns: int, before: resource.struct_rusage, after: resource.struct_rusage) -> OperationReport:
        elapsed = max(0, (time.monotonic_ns() - start_ns) // 1_000_000)
        cpu = max(0, round(((after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)) * 1000))
        rss = max(0, after.ru_maxrss - before.ru_maxrss)
        return OperationReport(elapsed_ms=elapsed, cpu_ms=cpu, peak_rss=rss, availability="PARTIAL")

    @staticmethod
    def axis_diff(manifest: EvaluationManifest) -> tuple[ComparisonMode, str | None, tuple[str, ...]]:
        baseline, candidate = sorted(manifest.subjects, key=lambda item: item.subject)
        changes = []
        for prefix, left, right in (("ingestion", baseline.ingestion_plan, candidate.ingestion_plan), ("query", baseline.query_plan, candidate.query_plan)):
            for key in sorted(set(left) | set(right)):
                if left.get(key) != right.get(key): changes.append(f"{prefix}.{key}")
        if not changes: raise ValueError("comparison subjects have no changed axis")
        if len(changes) == 1: return ComparisonMode.SINGLE_AXIS, changes[0], tuple(changes)
        if not manifest.experiment_name: raise ValueError("multi-axis comparison requires experiment name")
        return ComparisonMode.MULTI_AXIS_NON_CAUSAL, None, tuple(changes)

    @staticmethod
    def delta(baseline: float | None, candidate: float | None) -> Delta:
        if baseline is None or candidate is None: return Delta(baseline=baseline, candidate=candidate, absolute=None, relative=None, relative_state="NOT_MEANINGFUL")
        absolute = candidate - baseline
        if baseline == 0: return Delta(baseline=baseline, candidate=candidate, absolute=absolute, relative=None, relative_state="UNDEFINED_BASELINE_ZERO")
        return Delta(baseline=baseline, candidate=candidate, absolute=absolute, relative=absolute / abs(baseline), relative_state="VALUE")

    @staticmethod
    def replay_observation(original: bytes, replayed: bytes, expected_runtime_digest: str | None = None, observed_runtime_digest: str | None = None) -> ReplayObservation:
        def deterministic(raw: bytes) -> dict:
            payload = json.loads(raw)
            payload.pop("operation", None)
            payload.pop("aggregate_ids", None)
            for gate in payload.get("gate_results", []):
                gate.pop("aggregate_id", None)
            return payload
        old, new = digest(deterministic(original)), digest(deterministic(replayed))
        environment_changed = expected_runtime_digest is not None and observed_runtime_digest is not None and expected_runtime_digest != observed_runtime_digest
        return ReplayObservation(state="ENVIRONMENT_CHANGED" if environment_changed else "STABLE" if old == new else "MODEL_OUTPUT_CHANGED", original_digest=old, replay_digest=new, expected_runtime_digest=expected_runtime_digest, observed_runtime_digest=observed_runtime_digest)

    @staticmethod
    async def _checked(artifacts: object, artifact_id: UUID, artifact_type: str, expected_digest: str | None = None) -> object:
        manifest = await artifacts.get_artifact_manifest(artifact_id)
        if not manifest or manifest.artifact_type != artifact_type or manifest.schema_revision != "v1":
            raise ValueError("pinned artifact identity is invalid")
        raw = await artifacts.read_content(artifact_id)
        if hashlib.sha256(raw).hexdigest() != manifest.content_digest or (expected_digest and manifest.content_digest != expected_digest):
            raise ValueError("pinned artifact digest is invalid")
        return manifest

    @staticmethod
    def _snapshot_dataset(raw: bytes) -> DatasetContent:
        try:
            envelope = json.loads(raw.decode("ascii"))
            if envelope.get("schema_version") != "GoldenDatasetSnapshot/v1":
                raise ValueError("dataset snapshot schema is invalid")
            dataset = DatasetContent.model_validate({key: envelope[key] for key in ("taxonomy", "annotations", "query_cases")})
            if envelope.get("content_digest") != hashlib.sha256(dataset_bytes(dataset)).hexdigest():
                raise ValueError("dataset snapshot content digest is invalid")
            return dataset
        except Exception as exc:
            raise ValueError("dataset snapshot content is invalid") from exc

    async def publish_manifest(self, manifest: EvaluationManifest, runs: object, artifacts: object) -> tuple[UUID, UUID]:
        """Validate every external pin before publishing an immutable manifest Artifact."""
        self._validate_plan_identities(manifest)
        dataset_manifest = await self._checked(artifacts, manifest.dataset_snapshot_id, "golden.dataset.snapshot", manifest.dataset_snapshot_digest)
        dataset = self._snapshot_dataset(await artifacts.read_content(manifest.dataset_snapshot_id))
        if manifest.taxonomy_digest != hashlib.sha256(dataset_bytes(dataset.taxonomy)).hexdigest():
            raise ValueError("manifest taxonomy does not match trusted snapshot")
        cases = {item.id: item for item in (*dataset.annotations, *dataset.query_cases)}
        if any(case_id not in cases or not DatasetService._is_reviewed(cases[case_id]) for case_id in manifest.case_ids):
            raise ValueError("dataset snapshot has unreviewed evaluation cases")
        all_bindings = tuple({(item.case_id, item.role, item.artifact_id, item.content_digest): item for subject in manifest.subjects for item in subject.bindings}.values())
        if any(not any(binding.role == "source" and binding.case_id == case_id for binding in subject.bindings) for subject in manifest.subjects for case_id in manifest.case_ids):
            raise ValueError("evaluation subject is missing required source binding")
        for binding in all_bindings:
            await self._checked(artifacts, binding.artifact_id, binding.artifact_type, binding.content_digest)
        # Catalog is itself a verifiable immutable input and prevents a manifest
        # from pretending a partial direct-parent list is complete.
        catalog_payload = {"schema_version": "EvaluationInputCatalog/v1", "bindings": [x.model_dump(mode="json") for x in sorted(all_bindings, key=lambda x: (x.case_id or "", x.role, str(x.artifact_id)))]}
        if digest(catalog_payload) != manifest.input_catalog_digest:
            raise ValueError("input catalog digest does not match manifest inventory")
        run_id = await runs.create_run(EngineKind.EVALUATION, {"kind": "evaluation_manifest", "manifest_digest": digest(manifest), "dataset": str(manifest.dataset_snapshot_id)})
        leaves = self.catalog_levels(all_bindings)
        catalog_ids: list[UUID] = []
        for number, leaf in enumerate(leaves[0]):
            raw = canonical_bytes({"schema_version": "EvaluationInputCatalog/v1", "bindings": [x.model_dump(mode="json") for x in leaf]})
            attempt, _ = await runs.start_attempt(run_id, f"evaluation.catalog.{number}", tuple(x.artifact_id for x in leaf))
            output = ArtifactInput(artifact_type="evaluation.input.catalog", schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), producing_plugin_id="evaluation.catalog@1", configuration_digest=plan_digest({"leaf": number}), parent_artifact_ids=tuple(x.artifact_id for x in leaf), summary="evaluation input catalog")
            catalog_ids.append((await artifacts.complete_with_outputs(run_id, attempt, ((output, raw),), summary="evaluation input catalog"))[0])
        raw = canonical_bytes(manifest)
        parents = (manifest.dataset_snapshot_id, *catalog_ids)
        attempt, _ = await runs.start_attempt(run_id, "evaluation.manifest", parents)
        output = ArtifactInput(artifact_type="evaluation.manifest", schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), producing_plugin_id="evaluation.manifest@1", configuration_digest=plan_digest({"manifest_digest": digest(manifest)}), parent_artifact_ids=parents, summary="immutable evaluation manifest")
        identifier = (await artifacts.complete_with_outputs(run_id, attempt, ((output, raw),), summary="evaluation manifest"))[0]
        await runs.finish_run(run_id, True)
        return run_id, identifier

    async def orchestrate(self, manifest_id: UUID, reports: tuple[tuple[UUID, MetricReport] | SubjectMetricReport, ...] | None, runs: object, artifacts: object) -> tuple[UUID, UUID, LayeredReport]:
        manifest_ref = await self._checked(artifacts, manifest_id, "evaluation.manifest")
        manifest = EvaluationManifest.model_validate_json(await artifacts.read_content(manifest_id))
        # Recheck every pin on every execution/replay, rather than trusting a prior publish.
        await self.publish_validation(manifest, artifacts)
        run_id = await runs.create_run(EngineKind.EVALUATION, {"kind": "evaluation_run", "manifest_id": str(manifest_id), "manifest_digest": manifest_ref.content_digest, "case_ids": list(manifest.case_ids), "metrics": list(manifest.metric_ids)})
        if reports is None:
            if self.metric_dispatcher is None:
                raise ValueError("evaluation metric dispatcher is required")
            dispatched = await self.metric_dispatcher(manifest, run_id)
            reports = tuple(dispatched)
        if self.registered_metrics and set(manifest.metric_ids) - set(self.registered_metrics):
            raise ValueError("metric is not registered")
        # A caller cannot fabricate a report object detached from its immutable
        # Artifact. The serialized contract, Artifact digest, and manifest pins
        # must all agree before it can influence a gate or comparison.
        verified: list[tuple[UUID, MetricReport]] = []
        report_subjects: dict[UUID, str] = {}
        for item in reports:
            explicit_subject: str | None = None
            if isinstance(item, SubjectMetricReport):
                identifier = item.metric_artifact_id; explicit_subject = item.subject
                supplied = MetricReport.model_validate_json(await artifacts.read_content(identifier))
            else:
                identifier, supplied = item
            record = await self._checked(artifacts, identifier, "metric.report")
            parsed = MetricReport.model_validate_json(await artifacts.read_content(identifier))
            if parsed != supplied or parsed.metric_id not in manifest.metric_ids or parsed.snapshot_artifact_id != manifest.dataset_snapshot_id or parsed.taxonomy_digest != manifest.taxonomy_digest or (parsed.owner != "ingestion" and parsed.case_id not in manifest.case_ids):
                raise ValueError("metric report does not match pinned evaluation inputs")
            if parsed.owner != "ingestion":
                required = [("evidence", parsed.label_evidence_artifact_id)]
                if parsed.question_source_artifact_id is not None:
                    required.append(("source", parsed.question_source_artifact_id))
                required.extend((role, artifact_id) for role, artifact_id in (("answer", parsed.answer_artifact_id), ("verification", parsed.verification_artifact_id), ("final_response", parsed.final_response_artifact_id), ("retrieval", parsed.measured_artifact_id)) if artifact_id is not None)
                candidates = [subject for subject in manifest.subjects if all(any(binding.case_id == parsed.case_id and binding.role == role and binding.artifact_id == artifact_id for binding in subject.bindings) for role, artifact_id in required)]
                if not candidates:
                    raise ValueError("metric report stage bindings are not pinned by the manifest")
                if explicit_subject is None and len(candidates) != 1:
                    raise ValueError("metric report subject attribution is ambiguous")
                if explicit_subject is not None:
                    subject = next(subject for subject in manifest.subjects if subject.subject == explicit_subject)
                    if not all(any(binding.case_id == parsed.case_id and binding.role == role and binding.artifact_id == artifact_id for binding in subject.bindings) for role, artifact_id in required):
                        raise ValueError("metric report subject attribution is not pinned")
                    report_subjects[identifier] = explicit_subject
                else:
                    report_subjects[identifier] = candidates[0].subject
            else:
                candidates = [subject for subject in manifest.subjects if any(binding.role == "ingestion" and binding.artifact_id == parsed.observed_artifact_id for binding in subject.bindings) and any(binding.role == "source" and binding.artifact_id == parsed.expected_artifact_id for binding in subject.bindings)]
                if explicit_subject is not None:
                    candidates = [subject for subject in candidates if subject.subject == explicit_subject]
                if len(candidates) != 1:
                    raise ValueError("ingestion metric report subject attribution is ambiguous")
                report_subjects[identifier] = candidates[0].subject
            roles = (("answer", parsed.answer_artifact_id), ("verification", parsed.verification_artifact_id), ("final_response", parsed.final_response_artifact_id), ("retrieval", parsed.measured_artifact_id))
            for role, artifact_id in roles:
                if artifact_id is not None and not any(any(binding.case_id == parsed.case_id and binding.role == role and binding.artifact_id == artifact_id for binding in subject.bindings) for subject in manifest.subjects):
                    raise ValueError("metric report stage bindings are not pinned by the manifest")
            verified.append((identifier, parsed))
        reports = tuple(verified)
        report_ids = tuple(identifier for identifier, _ in sorted(reports, key=lambda pair: str(pair[0])))
        start, before = time.monotonic_ns(), resource.getrusage(resource.RUSAGE_SELF)
        layers: dict[str, tuple[UUID, ...]] = {key: () for key in ("ingestion", "retrieval", "answer", "citation", "decision", "judge", "latency", "resources")}
        for identifier, item in reports:
            key = "retrieval" if item.owner == "context" else item.owner
            if key in layers: layers[key] = tuple(sorted((*layers[key], identifier), key=str))
        # Persist independent aggregates and policy/operation observations.
        aggregate_ids: list[UUID] = []
        aggregates: list[tuple[UUID, object]] = []
        partitioned_groups = []
        for subject in ("baseline", "candidate"):
            subset = tuple((identifier, report) for identifier, report in reports if report_subjects.get(identifier) == subject)
            partitioned_groups.extend((subject, metric_id, selector, group) for ((metric_id, selector), group) in self._aggregate_groups(subset))
        for number, (subject, metric_id, selector, group) in enumerate(partitioned_groups):
            aggregate = MetricAggregator().aggregate(tuple(group), metric_id, selector)
            aggregate_raw = metric_aggregate_bytes(aggregate)
            aggregate_parents = aggregate.report_artifact_ids if len(aggregate.report_artifact_ids) <= 64 else (await self._publish_report_catalog_tree(run_id, aggregate.report_artifact_ids, runs, artifacts),)
            aggregate_attempt, _ = await runs.start_attempt(run_id, f"evaluation.aggregate.{number}", aggregate_parents)
            aggregate_input = ArtifactInput(artifact_type="metric.aggregate", schema_revision="v1", content_digest=hashlib.sha256(aggregate_raw).hexdigest(), byte_size=len(aggregate_raw), producing_plugin_id="evaluation.aggregate@1", configuration_digest=plan_digest({"metric": metric_id, "selector": selector}), parent_artifact_ids=aggregate_parents, summary="evaluation metric aggregate")
            aggregate_id = (await artifacts.complete_with_outputs(run_id, aggregate_attempt, ((aggregate_input, aggregate_raw),), summary="evaluation metric aggregate"))[0]
            aggregate_ids.append(aggregate_id); aggregates.append((aggregate_id, aggregate))
        gate_results: list[GateResult] = []
        for number, (subject, gate) in enumerate((subject, gate) for subject in ("baseline", "candidate") for gate in manifest.gates):
            subject_reports = tuple((identifier, item) for identifier, item in reports if report_subjects.get(identifier) == subject)
            selected = tuple((identifier, item) for identifier, item in subject_reports if item.metric_id == gate.metric_id and item.owner == gate.owner and all(item.slices.get(k) == v for k, v in gate.selector.items()))
            result = self.evaluate_gate(gate, subject_reports)
            aggregate_id = None
            if selected:
                exact = MetricAggregator().aggregate(selected, gate.metric_id, gate.selector)
                exact_raw = metric_aggregate_bytes(exact)
                exact_parents = exact.report_artifact_ids if len(exact.report_artifact_ids) <= 64 else (await self._publish_report_catalog_tree(run_id, exact.report_artifact_ids, runs, artifacts),)
                exact_attempt, _ = await runs.start_attempt(run_id, f"evaluation.gate.aggregate.{number}", exact_parents)
                exact_input = ArtifactInput(artifact_type="metric.aggregate", schema_revision="v1", content_digest=hashlib.sha256(exact_raw).hexdigest(), byte_size=len(exact_raw), producing_plugin_id="evaluation.gate-aggregate@1", configuration_digest=plan_digest({"gate":gate.gate_id,"selector":gate.selector}), parent_artifact_ids=exact_parents, summary="exact gate metric aggregate")
                aggregate_id = (await artifacts.complete_with_outputs(run_id, exact_attempt, ((exact_input, exact_raw),), summary="exact gate metric aggregate"))[0]
                aggregate_ids.append(aggregate_id)
            counts = {"value": sum(item.status is MetricStatus.VALUE for _, item in selected), "not_applicable": sum(item.status is MetricStatus.NOT_APPLICABLE for _, item in selected), "insufficient_labels": sum(item.status is MetricStatus.INSUFFICIENT_LABELS for _, item in selected)}
            gate_results.append(result.model_copy(update={"subject": subject, "aggregate_id": aggregate_id, "state_counts": counts}))
        gates = tuple(gate_results)
        after = resource.getrusage(resource.RUSAGE_SELF)
        operation = self.operation(start, before, after)
        unvalidated_failed = self.failed_case_links(gates, reports, manifest, report_subjects)
        failed_items: list[FailedCaseLink] = []
        for link in unvalidated_failed:
            failed_items.append(await self.validate_failed_case_lineage(link, artifacts, evaluation_run_id=run_id))
        failed = tuple(failed_items)
        layered = LayeredReport(manifest_artifact_id=manifest_id, manifest_digest=manifest_ref.content_digest, report_ids=report_ids, aggregate_ids=tuple(aggregate_ids), report_subjects=report_subjects, layers=layers, gate_results=gates, operation=operation, failed_cases=failed)
        gate_raw = canonical_bytes({"schema_version":"EvaluationGateReport/v1", "gates":[item.model_dump(mode="json") for item in gates]})
        gate_parents = (manifest_id, *aggregate_ids, *report_ids)
        if len(gate_parents) > 64:
            gate_parents = (manifest_id, await self._publish_report_catalog_tree(run_id, tuple(gate_parents[1:]), runs, artifacts))
        gate_attempt, _ = await runs.start_attempt(run_id, "evaluation.gates", gate_parents)
        gate_input = ArtifactInput(artifact_type="evaluation.gate.report", schema_revision="v1", content_digest=hashlib.sha256(gate_raw).hexdigest(), byte_size=len(gate_raw), producing_plugin_id="evaluation.gates@1", configuration_digest=plan_digest({"manifest": str(manifest_id)}), parent_artifact_ids=gate_parents, summary="evaluation gate results")
        gate_id = (await artifacts.complete_with_outputs(run_id, gate_attempt, ((gate_input, gate_raw),), summary="evaluation gate results"))[0]
        operation_raw = canonical_bytes(operation)
        op_attempt, _ = await runs.start_attempt(run_id, "evaluation.operations", (manifest_id,))
        op_input = ArtifactInput(artifact_type="evaluation.operation.report", schema_revision="v1", content_digest=hashlib.sha256(operation_raw).hexdigest(), byte_size=len(operation_raw), producing_plugin_id="evaluation.operations@1", configuration_digest=plan_digest({"sampler": manifest.runtime.resource_sampler_version}), parent_artifact_ids=(manifest_id,), summary="evaluation local operation observation")
        operation_id = (await artifacts.complete_with_outputs(run_id, op_attempt, ((op_input, operation_raw),), summary="evaluation local operation observation"))[0]
        raw = canonical_bytes(layered)
        parents = (manifest_id, gate_id, operation_id, *aggregate_ids, *report_ids)
        # Artifact parent limits are strict. One catalog parent represents report fan-out.
        if len(parents) > 64:
            catalog_raw = canonical_bytes({"schema_version":"EvaluationReportCatalog/v1", "report_ids":[str(x) for x in report_ids]})
            # Chunk all reports, then recursively catalog child catalogs. No IDs
            # are omitted simply because direct Artifact parents are bounded.
            catalog_id = await self._publish_report_catalog_tree(run_id, report_ids, runs, artifacts)
            parents = (manifest_id, gate_id, operation_id, catalog_id)
        attempt, _ = await runs.start_attempt(run_id, "evaluation.report", parents)
        output = ArtifactInput(artifact_type="evaluation.report", schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), producing_plugin_id="evaluation.orchestrator@1", configuration_digest=plan_digest({"manifest": str(manifest_id), "report_count": len(report_ids)}), parent_artifact_ids=parents, summary="layered evaluation report")
        report_id = (await artifacts.complete_with_outputs(run_id, attempt, ((output, raw),), summary="layered evaluation report"))[0]
        # Artifact IDs exist only after publication, so the separate immutable
        # index is the authoritative navigation object rather than a
        # self-referential report payload.
        indexed_links: list[FailedCaseLink] = []
        for link in failed:
            indexed_links.append(await self.validate_failed_case_lineage(link, artifacts, evaluation_report_id=report_id, evaluation_run_id=run_id))
        navigation = NavigationIndex(evaluation_report_id=report_id, evaluation_run_id=run_id, links=tuple(indexed_links))
        navigation_raw = canonical_bytes(navigation)
        navigation_parents = (report_id, *tuple(link.metric_report_id for link in indexed_links if link.metric_report_id is not None), *aggregate_ids)
        if len(navigation_parents) > 64:
            navigation_parents = (report_id, await self._publish_report_catalog_tree(run_id, tuple(navigation_parents[1:]), runs, artifacts))
        nav_attempt, _ = await runs.start_attempt(run_id, "evaluation.navigation", navigation_parents)
        nav_input = ArtifactInput(artifact_type="evaluation.navigation.index", schema_revision="v1", content_digest=hashlib.sha256(navigation_raw).hexdigest(), byte_size=len(navigation_raw), producing_plugin_id="evaluation.navigation@1", configuration_digest=plan_digest({"report": str(report_id), "run": str(run_id)}), parent_artifact_ids=navigation_parents, summary="evaluation failed-case navigation")
        await artifacts.complete_with_outputs(run_id, nav_attempt, ((nav_input, navigation_raw),), summary="evaluation failed-case navigation")
        await runs.finish_run(run_id, True)
        return run_id, report_id, layered

    async def publish_validation(self, manifest: EvaluationManifest, artifacts: object) -> None:
        await self._checked(artifacts, manifest.dataset_snapshot_id, "golden.dataset.snapshot", manifest.dataset_snapshot_digest)
        dataset = self._snapshot_dataset(await artifacts.read_content(manifest.dataset_snapshot_id))
        if manifest.taxonomy_digest != hashlib.sha256(dataset_bytes(dataset.taxonomy)).hexdigest():
            raise ValueError("manifest taxonomy does not match trusted snapshot")
        cases = {item.id: item for item in (*dataset.annotations, *dataset.query_cases)}
        if any(case_id not in cases or not DatasetService._is_reviewed(cases[case_id]) for case_id in manifest.case_ids):
            raise ValueError("dataset snapshot has unreviewed evaluation cases")
        inventory = tuple({(x.case_id, x.role, x.artifact_id, x.content_digest): x for subject in manifest.subjects for x in subject.bindings}.values())
        payload = {"schema_version": "EvaluationInputCatalog/v1", "bindings": [x.model_dump(mode="json") for x in sorted(inventory, key=lambda x: (x.case_id or "", x.role, str(x.artifact_id)))]}
        if digest(payload) != manifest.input_catalog_digest:
            raise ValueError("input catalog digest does not match manifest inventory")
        if self.registered_metrics and set(manifest.metric_ids) - set(self.registered_metrics):
            raise ValueError("metric is not registered")
        self._validate_plan_identities(manifest)
        for subject in manifest.subjects:
            for binding in subject.bindings:
                await self._checked(artifacts, binding.artifact_id, binding.artifact_type, binding.content_digest)

    @staticmethod
    def _validate_plan_identities(manifest: EvaluationManifest) -> None:
        for subject in manifest.subjects:
            identities = {item.plugin_id: item for item in subject.declared_identities}
            for plan in (subject.ingestion_plan, subject.query_plan):
                plugin = plan.get("plugin")
                identity = identities.get(plugin) if isinstance(plugin, str) else None
                if identity is None:
                    raise ValueError("resolved plan plugin identity is not declared")
                if plan.get("implementation_digest") is not None and plan["implementation_digest"] != identity.implementation_digest:
                    raise ValueError("resolved plan implementation identity is mismatched")
                if plan.get("configuration_digest") is not None and plan["configuration_digest"] != identity.configuration_digest:
                    raise ValueError("resolved plan configuration identity is mismatched")
                if plan.get("model") is not None and plan["model"] != identity.model:
                    raise ValueError("resolved plan model identity is mismatched")
                if plan.get("prompt_digest") is not None and plan["prompt_digest"] != identity.prompt_digest:
                    raise ValueError("resolved plan prompt identity is mismatched")

    @staticmethod
    def _aggregate_groups(reports: tuple[tuple[UUID, MetricReport], ...]) -> tuple[tuple[tuple[str, dict[str, str]], tuple[tuple[UUID, MetricReport], ...]], ...]:
        groups: dict[tuple[str, tuple[tuple[str, str], ...]], list[tuple[UUID, MetricReport]]] = {}
        for identifier, report in reports:
            key = (report.metric_id, tuple(sorted(report.slices.items())))
            groups.setdefault(key, []).append((identifier, report))
        return tuple(((metric, dict(selector)), tuple(items)) for (metric, selector), items in sorted(groups.items()))

    async def _publish_report_catalog_tree(self, run_id: UUID, report_ids: tuple[UUID, ...], runs: object, artifacts: object) -> UUID:
        current: tuple[UUID, ...] = tuple(sorted(report_ids, key=str))
        level = 0
        while len(current) > 1:
            next_level: list[UUID] = []
            for index in range(0, len(current), 64):
                parents = current[index:index + 64]
                raw = canonical_bytes({"schema_version":"EvaluationReportCatalog/v1", "level":level, "children":[str(x) for x in parents]})
                attempt, _ = await runs.start_attempt(run_id, f"evaluation.report.catalog.{level}.{index // 64}", parents)
                output = ArtifactInput(artifact_type="evaluation.report.catalog", schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), producing_plugin_id="evaluation.report-catalog@1", configuration_digest=plan_digest({"level":level,"count":len(parents)}), parent_artifact_ids=parents, summary="evaluation report catalog")
                next_level.append((await artifacts.complete_with_outputs(run_id, attempt, ((output, raw),), summary="evaluation report catalog"))[0])
            current = tuple(next_level)
            level += 1
        return current[0]

    @staticmethod
    def failed_case_links(gates: tuple[GateResult, ...], reports: tuple[tuple[UUID, MetricReport], ...], manifest: EvaluationManifest, report_subjects: dict[UUID, str] | None = None) -> tuple[FailedCaseLink, ...]:
        links: list[FailedCaseLink] = []
        for gate in gates:
            if gate.state is not GateState.FAIL: continue
            for report_id, report in reports:
                if report_id not in gate.selected_report_ids or not report.case_id: continue
                declared = (report_subjects or {}).get(report_id)
                candidates = [x for x in manifest.subjects if (declared is None or x.subject == declared) and any(binding.role == "evidence" and binding.artifact_id == report.label_evidence_artifact_id and binding.case_id == report.case_id for binding in x.bindings) and (report.question_source_artifact_id is None or any(binding.role == "source" and binding.artifact_id == report.question_source_artifact_id and binding.case_id == report.case_id for binding in x.bindings))]
                if len(candidates) != 1:
                    raise ValueError("failed case subject cannot be proven from pinned bindings")
                subject = candidates[0].subject
                bindings = next((x.bindings for x in manifest.subjects if x.subject == subject), ())
                by_role = {x.role: x.artifact_id for x in bindings if x.case_id == report.case_id}
                links.append(FailedCaseLink(case_id=report.case_id, subject=subject, gate_id=gate.gate_id, metric_report_id=report_id, source_artifact_id=by_role.get("source"), ingestion_artifact_id=by_role.get("ingestion"), retrieval_artifact_id=by_role.get("retrieval"), fusion_artifact_id=by_role.get("fusion"), rerank_artifact_id=by_role.get("rerank"), evidence_artifact_id=report.label_evidence_artifact_id, generation_artifact_id=report.answer_artifact_id, verification_artifact_id=report.verification_artifact_id, final_response_artifact_id=report.final_response_artifact_id))
        return tuple(sorted(links, key=lambda item: (item.case_id, item.gate_id, str(item.metric_report_id))))

    async def validate_failed_case_lineage(self, link: FailedCaseLink, artifacts: object, *, evaluation_report_id: UUID | None = None, evaluation_run_id: UUID | None = None) -> FailedCaseLink:
        """Validate the navigable, typed parent chain without copying any bodies.

        Optional stages remain explicitly absent. Present stages must have their
        expected schema and every downstream parent relation must be provable.
        """
        expected = ((link.source_artifact_id, "canonical.document"), (link.retrieval_artifact_id, "retrieval.candidate.set"), (link.fusion_artifact_id, "fusion.candidate.set"), (link.rerank_artifact_id, "rerank.candidate.set"), (link.evidence_artifact_id, "evidence.set"), (link.generation_artifact_id, "generated.answer"), (link.verification_artifact_id, "verification.result"), (link.final_response_artifact_id, "final.response"), (link.metric_report_id, "metric.report"))
        manifests: dict[UUID, object] = {}
        for identifier, artifact_type in expected:
            if identifier is None:
                continue
            manifests[identifier] = await self._checked(artifacts, identifier, artifact_type)
        if link.ingestion_artifact_id is not None:
            ingestion = await artifacts.get_artifact_manifest(link.ingestion_artifact_id)
            allowed_ingestion = {"canonical.document", "chunk.set", "embedding.set", "search.document.set", "search.index.result"}
            if not ingestion or ingestion.schema_revision != "v1" or ingestion.artifact_type not in allowed_ingestion:
                raise ValueError("failed case ingestion artifact identity is invalid")
            raw = await artifacts.read_content(link.ingestion_artifact_id)
            if hashlib.sha256(raw).hexdigest() != ingestion.content_digest:
                raise ValueError("failed case ingestion artifact digest is invalid")
            manifests[link.ingestion_artifact_id] = ingestion
        def parent(child: UUID | None, *parents: UUID | None) -> None:
            if child is None: return
            actual = set(manifests[child].parent_artifact_ids)
            present = {item for item in parents if item is not None}
            if present and not (actual & present):
                raise ValueError("failed case artifact lineage is mismatched")
        parent(link.ingestion_artifact_id, link.source_artifact_id)
        parent(link.fusion_artifact_id, link.retrieval_artifact_id)
        parent(link.rerank_artifact_id, link.fusion_artifact_id, link.retrieval_artifact_id)
        parent(link.evidence_artifact_id, link.rerank_artifact_id, link.fusion_artifact_id, link.retrieval_artifact_id)
        parent(link.generation_artifact_id, link.evidence_artifact_id)
        parent(link.verification_artifact_id, link.generation_artifact_id, link.evidence_artifact_id)
        parent(link.final_response_artifact_id, link.verification_artifact_id, link.generation_artifact_id, link.evidence_artifact_id)
        parent(link.metric_report_id, link.final_response_artifact_id, link.evidence_artifact_id)
        if evaluation_report_id is not None:
            report = await self._checked(artifacts, evaluation_report_id, "evaluation.report")
            if link.metric_report_id not in report.parent_artifact_ids and not any(parent_id == link.metric_report_id for parent_id in report.parent_artifact_ids):
                # A catalog may be the direct parent; callers retain the catalog
                # traversal separately, so direct report parents are required for
                # bounded direct-report publications only.
                if len(report.parent_artifact_ids) < 64: raise ValueError("evaluation report lineage is mismatched")
        return link.model_copy(update={"evaluation_report_id": evaluation_report_id, "evaluation_run_id": evaluation_run_id})

    async def replay(self, manifest_id: UUID, reports: tuple[tuple[UUID, MetricReport], ...] | None, runs: object, artifacts: object, *, original_report_id: UUID | None = None, observed_runtime_digest: str | None = None) -> tuple[UUID, UUID, ReplayObservation]:
        await self._checked(artifacts, manifest_id, "evaluation.manifest")
        manifest = EvaluationManifest.model_validate_json(await artifacts.read_content(manifest_id))
        if original_report_id is None:
            raise ValueError("replay requires original evaluation report")
        original = await self._checked(artifacts, original_report_id, "evaluation.report")
        run_id, report_id, _ = await self.orchestrate(manifest_id, reports, runs, artifacts)
        replayed = await self._checked(artifacts, report_id, "evaluation.report")
        observation = self.replay_observation(await artifacts.read_content(original_report_id), await artifacts.read_content(report_id), manifest.runtime.runtime_digest, observed_runtime_digest or manifest.runtime.runtime_digest)
        raw = canonical_bytes(observation)
        attempt, _ = await runs.start_attempt(run_id, "evaluation.replay.observation", (manifest_id, report_id))
        output = ArtifactInput(artifact_type="evaluation.replay.observation", schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), producing_plugin_id="evaluation.replay@1", configuration_digest=plan_digest({"state": observation.state, "expected_runtime": manifest.runtime.runtime_digest, "observed_runtime": observation.observed_runtime_digest}), parent_artifact_ids=(manifest_id, original_report_id, report_id), summary="evaluation replay observation")
        observation_id = (await artifacts.complete_with_outputs(run_id, attempt, ((output, raw),), summary="evaluation replay observation"))[0]
        return run_id, observation_id, observation

    async def compare(self, baseline_report_id: UUID, candidate_report_id: UUID, runs: object, artifacts: object) -> tuple[UUID, UUID, ComparisonResult]:
        """Persist a comparison only after proving the two reports share fixed inputs."""
        baseline_ref = await self._checked(artifacts, baseline_report_id, "evaluation.report")
        candidate_ref = await self._checked(artifacts, candidate_report_id, "evaluation.report")
        baseline = LayeredReport.model_validate_json(await artifacts.read_content(baseline_report_id))
        candidate = LayeredReport.model_validate_json(await artifacts.read_content(candidate_report_id))
        baseline_manifest = EvaluationManifest.model_validate_json(await artifacts.read_content(baseline.manifest_artifact_id))
        candidate_manifest = EvaluationManifest.model_validate_json(await artifacts.read_content(candidate.manifest_artifact_id))
        fixed = ("dataset_snapshot_id", "dataset_snapshot_digest", "taxonomy_digest", "input_catalog_digest", "case_ids", "metric_ids", "gates", "runtime", "confidence_policy")
        if any(getattr(baseline_manifest, key) != getattr(candidate_manifest, key) for key in fixed):
            raise ValueError("comparison inputs are not pinned-equivalent")
        mode, axis, changes = self.axis_diff(EvaluationManifest.model_validate(baseline_manifest.model_dump() | {"subjects": (baseline_manifest.subjects[0], candidate_manifest.subjects[1]), "experiment_name": candidate_manifest.experiment_name or baseline_manifest.experiment_name}))
        # Reports retain values elsewhere; comparison contains only transparent deltas.
        deltas = (
            self.delta(baseline.operation.elapsed_ms, candidate.operation.elapsed_ms),
            self.delta(baseline.operation.cpu_ms, candidate.operation.cpu_ms),
            self.delta(baseline.operation.peak_rss, candidate.operation.peak_rss),
        )
        hard_failed = any(item.state is not GateState.PASS for item in candidate.gate_results)
        result = ComparisonResult(mode=mode, axis=axis, changes=changes, deltas=deltas, recommendation="BASELINE_RETAINED" if hard_failed else "CANDIDATE_ELIGIBLE")
        async def quality(report: LayeredReport) -> list[dict]:
            values: list[dict] = []
            for identifier in report.report_ids:
                await self._checked(artifacts, identifier, "metric.report")
                item = MetricReport.model_validate_json(await artifacts.read_content(identifier))
                values.append({"subject": report.report_subjects.get(identifier), "metric_id": item.metric_id, "owner": item.owner, "case_id": item.case_id, "slices": item.slices, "status": item.status, "value": item.value, "sample_count": item.sample_count, "labelled_count": item.labelled_count, "matched_count": item.matched_count})
            return sorted(values, key=lambda item: (item["metric_id"], item["case_id"] or "", str(item["slices"])))
        baseline_quality, candidate_quality = await quality(baseline), await quality(candidate)
        by_key = lambda values: {(item["subject"], item["metric_id"], item["owner"], item["case_id"], tuple(sorted(item["slices"].items()))): item for item in values}
        bmap, cmap = by_key(baseline_quality), by_key(candidate_quality)
        quality_deltas = [{"key": list(key), "delta": self.delta(bmap.get(key, {}).get("value"), cmap.get(key, {}).get("value")).model_dump(mode="json")} for key in sorted(set(bmap) | set(cmap), key=str)]
        def confidence(values: list[dict], policy: object | None) -> dict:
            if policy is None or policy.kind == "none":
                return {"state":"NOT_MEANINGFUL", "reason":"POLICY_NONE"}
            binary = [item for item in values if item["owner"] in {"decision", "citation"} and item["status"] == "VALUE" and item["labelled_count"] > 0]
            if len(binary) != 1:
                return {"state":"NOT_MEANINGFUL", "reason":"UNSUPPORTED_AGGREGATE"}
            item = binary[0]; n, successes = item["labelled_count"], item["matched_count"]
            z = NormalDist().inv_cdf((1 + policy.level) / 2); p = successes / n
            denominator = 1 + z * z / n
            center = (p + z * z / (2 * n)) / denominator
            radius = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** .5) / denominator
            return {"state":"VALUE", "method":"wilson", "level":policy.level, "numerator":successes, "denominator":n, "lower":max(0, center-radius), "upper":min(1, center+radius)}
        confidence_context = {"baseline":confidence(baseline_quality, baseline_manifest.confidence_policy), "candidate":confidence(candidate_quality, candidate_manifest.confidence_policy)}
        run_id = await runs.create_run(EngineKind.EVALUATION, {"kind": "evaluation_comparison", "baseline": str(baseline_report_id), "candidate": str(candidate_report_id)})
        raw = canonical_bytes({"schema_version":"EvaluationComparison/v1", "baseline_report_id":str(baseline_report_id), "candidate_report_id":str(candidate_report_id), "mode":result.mode, "axis":result.axis, "changes":result.changes, "deltas":[item.model_dump(mode="json") for item in result.deltas], "quality":{"baseline":baseline_quality,"candidate":candidate_quality,"deltas":quality_deltas}, "confidence":confidence_context, "layers":{"baseline":baseline.layers,"candidate":candidate.layers}, "metric_report_ids":{"baseline":[str(x) for x in baseline.report_ids],"candidate":[str(x) for x in candidate.report_ids]}, "gates":{"baseline":[x.model_dump(mode="json") for x in baseline.gate_results],"candidate":[x.model_dump(mode="json") for x in candidate.gate_results]}, "failed_cases":{"baseline":[x.model_dump(mode="json") for x in baseline.failed_cases],"candidate":[x.model_dump(mode="json") for x in candidate.failed_cases]}, "latency":{"baseline":baseline.operation.elapsed_ms,"candidate":candidate.operation.elapsed_ms}, "resources":{"baseline":baseline.operation.model_dump(mode="json", exclude={"elapsed_ms"}),"candidate":candidate.operation.model_dump(mode="json", exclude={"elapsed_ms"})}, "recommendation":result.recommendation})
        attempt, _ = await runs.start_attempt(run_id, "evaluation.comparison", (baseline_report_id, candidate_report_id))
        output = ArtifactInput(artifact_type="evaluation.comparison", schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), producing_plugin_id="evaluation.comparison@1", configuration_digest=plan_digest({"baseline": baseline_ref.content_digest, "candidate": candidate_ref.content_digest}), parent_artifact_ids=(baseline_report_id, candidate_report_id), summary="immutable evaluation comparison")
        comparison_id = (await artifacts.complete_with_outputs(run_id, attempt, ((output, raw),), summary="evaluation comparison"))[0]
        await runs.finish_run(run_id, True)
        return run_id, comparison_id, result
