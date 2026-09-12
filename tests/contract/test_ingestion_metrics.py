from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from kb2_runtime.canonical.contracts import CanonicalDocument
from kb2_runtime.chunking.contracts import ChunkerConfig
from kb2_runtime.chunking.processor import process
from kb2_runtime.evaluation.datasets.contracts import AnnotationTarget, CaseOrigin, CaseProvenance, DocumentAnnotation, SourceArtifactRef
from kb2_runtime.evaluation.ingestion import IngestionMetricPlugin, IngestionMetricService, METRICS, MetricAggregator, MetricReport, MetricStatus, metric_report_bytes
from kb2_runtime.plugins.bootstrap import EmptyConfig, bootstrap_registry
from kb2_runtime.plugins.contracts import PluginDescriptor, PluginInvocationResult, PluginOutput, RunnerType
from kb2_runtime.plugins.executor import PluginExecutor
from kb2_runtime.plugins.runner import InProcessRunner
from kb2_runtime.trace.contracts import ArtifactManifest, ArtifactReference, SafeError


def document() -> CanonicalDocument:
    return CanonicalDocument.model_validate_json((Path(__file__).parents[1] / "fixtures" / "ingestion" / "long-hierarchy-canonical.json").read_bytes())


def annotation(kind: str = "text_span") -> DocumentAnnotation:
    source = SourceArtifactRef(id=uuid4(), artifact_type="canonical.document", content_digest="a" * 64)
    target = AnnotationTarget(kind=kind, element_id="elm_0000000000000002", start=0, end=5) if kind == "text_span" else AnnotationTarget(kind=kind, element_id="elm_0000000000000002")
    return DocumentAnnotation(id="ann_0123456789abcdef", source=source, slices={"format":"docx", "processing_class":"native", "native_ocr":"native", "structure":"prose", "language":"en", "question_class":"lookup", "difficulty":"low", "criticality":"low"}, provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), target=target, label="Intro")


def report(status: MetricStatus, value: float | None, document_id: str = "doc_0000000000000001", taxonomy_digest: str = "b" * 64) -> MetricReport:
    identifier = uuid4()
    return MetricReport(metric_id="metric.ingestion.cer@1", required_annotation_kinds=("text_span",), document_id=document_id, snapshot_artifact_id=identifier, expected_artifact_id=uuid4(), observed_artifact_id=uuid4(), taxonomy_digest=taxonomy_digest, slices=annotation().slices, status=status, value=value, elapsed_ms=0, labelled_count=1, matched_count=1 if value == 1 else 0)


def table_document() -> CanonicalDocument:
    return CanonicalDocument.model_validate_json((Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes())


def metric_annotation(kind: str, expected: CanonicalDocument) -> DocumentAnnotation:
    if kind == "text_span": target = AnnotationTarget(kind=kind, element_id="elm_0000000000000002", start=0, end=5)
    elif kind in {"element", "reading_order", "evidence_coverage"}: target = AnnotationTarget(kind=kind, element_id="elm_0000000000000002")
    elif kind == "table": target = AnnotationTarget(kind=kind, table_id="tbl_0000000000000021")
    elif kind == "cell": target = AnnotationTarget(kind=kind, table_id="tbl_0000000000000021", cell_id="cel_0000000000000024")
    else: target = AnnotationTarget(kind=kind, locator=expected.elements[1].locator)
    return annotation().model_copy(update={"target": target})


def test_baseline_metrics_are_registered_and_cer_is_deterministic() -> None:
    registry = bootstrap_registry()
    assert set(METRICS) <= {item.plugin_id for item in registry.inspect()}
    metric = IngestionMetricPlugin("metric.ingestion.cer@1")
    perfect = metric._score("text_span", (annotation(),), document(), document())
    degraded = document().model_copy(update={"elements": tuple(item.model_copy(update={"text": "xxxxx"}) if item.id == "elm_0000000000000002" else item for item in document().elements)})
    assert perfect == (1.0, 1)
    assert metric._score("text_span", (annotation(),), document(), degraded) == (0.0, 0)


def test_missing_states_are_explicit_and_reports_are_canonical() -> None:
    not_applicable = report(MetricStatus.NOT_APPLICABLE, None)
    insufficient = report(MetricStatus.INSUFFICIENT_LABELS, None)
    assert metric_report_bytes(not_applicable) == metric_report_bytes(MetricReport.model_validate_json(metric_report_bytes(not_applicable)))
    with pytest.raises(ValueError):
        report(MetricStatus.NOT_APPLICABLE, 0.0)
    assert insufficient.status is MetricStatus.INSUFFICIENT_LABELS


def test_metric_payloads_reject_unknown_schema_versions() -> None:
    with pytest.raises(ValueError):
        MetricReport.model_validate({**report(MetricStatus.VALUE, 1.0).model_dump(), "schema_version": "MetricReport/v9"})


def test_aggregation_keeps_zero_and_missing_counts_separate() -> None:
    reports = ((uuid4(), report(MetricStatus.VALUE, 1.0, "doc_0000000000000001")), (uuid4(), report(MetricStatus.VALUE, 0.0, "doc_0000000000000002")), (uuid4(), report(MetricStatus.NOT_APPLICABLE, None, "doc_0000000000000003")), (uuid4(), report(MetricStatus.INSUFFICIENT_LABELS, None, "doc_0000000000000004")))
    aggregate = MetricAggregator().aggregate(reports, "metric.ingestion.cer@1", {"language": "en"})
    assert (aggregate.document_count, aggregate.scored_count, aggregate.not_applicable_count, aggregate.insufficient_labels_count, aggregate.value) == (4, 2, 1, 1, 0.5)
    only_missing = MetricAggregator().aggregate(reports[2:], "metric.ingestion.cer@1", {"language": "en"})
    assert only_missing.value is None and only_missing.scored_count == 0


@pytest.mark.parametrize(
    ("metric_id", "kind", "expected_factory", "observed_factory"),
    [
        ("metric.ingestion.cer@1", "text_span", document, document),
        ("metric.ingestion.wer@1", "text_span", document, document),
        ("metric.ingestion.element-f1@1", "element", document, document),
        ("metric.ingestion.reading-order@1", "reading_order", document, document),
        ("metric.ingestion.table-structure@1", "table", table_document, table_document),
        ("metric.ingestion.table-cell@1", "cell", table_document, table_document),
        ("metric.ingestion.locator-accuracy@1", "locator", document, document),
    ],
)
def test_each_canonical_baseline_metric_has_a_perfect_golden_fixture(metric_id, kind, expected_factory, observed_factory) -> None:
    expected, observed = expected_factory(), observed_factory()
    labels = (metric_annotation(kind, expected),)
    if kind == "reading_order":
        labels = (labels[0], annotation("reading_order").model_copy(update={"target": AnnotationTarget(kind="reading_order", element_id="elm_0000000000000003")}))
    value, matched = IngestionMetricPlugin(metric_id)._score(kind, labels, expected, observed)
    assert value == 1.0 and matched > 0


def test_evidence_preservation_has_perfect_and_failed_golden_fixtures() -> None:
    expected = document()
    chunks = process(expected.model_dump_json().encode(), ChunkerConfig(strategy="fixed_window", max_tokens=64))
    label = metric_annotation("evidence_coverage", expected)
    perfect = IngestionMetricPlugin("metric.ingestion.evidence-preservation@1")._score("evidence_coverage", (label,), expected, chunks)
    missing = chunks.model_copy(update={"chunks": tuple(chunk.model_copy(update={"citations": tuple(item for item in chunk.citations if item.element_id != label.target.element_id)}) for chunk in chunks.chunks)})
    failed = IngestionMetricPlugin("metric.ingestion.evidence-preservation@1")._score("evidence_coverage", (label,), expected, missing)
    assert perfect == (1.0, 1) and failed == (0.0, 0)


def test_aggregator_rejects_mixed_metric_and_unknown_slice_reports() -> None:
    first = report(MetricStatus.VALUE, 1.0)
    other_metric = first.model_copy(update={"metric_id": "metric.ingestion.wer@1"})
    with pytest.raises(ValueError):
        MetricAggregator().aggregate(((uuid4(), first), (uuid4(), other_metric)), first.metric_id, {"language": "en"})
    with pytest.raises(ValueError):
        MetricAggregator().aggregate(((uuid4(), first),), first.metric_id, {"made_up": "value"})


def test_aggregator_rejects_reports_from_incompatible_snapshot_taxonomies() -> None:
    first = report(MetricStatus.VALUE, 1.0)
    incompatible = first.model_copy(update={"document_id": "doc_0000000000000002", "taxonomy_digest": "a" * 64})
    with pytest.raises(ValueError, match="taxonomies"):
        MetricAggregator().aggregate(((uuid4(), first), (uuid4(), incompatible)), first.metric_id, {"language": "en"})
    with pytest.raises(ValueError):
        MetricAggregator().aggregate(((uuid4(), first), (uuid4(), report(MetricStatus.VALUE, 1.0, "doc_0000000000000002", "c" * 64))), first.metric_id, {"language": "en"})


class _Runs:
    def __init__(self) -> None:
        self.attempt, self.failures = uuid4(), []

    async def start_attempt(self, run_id, stage_key, parents=()): return self.attempt, 1
    async def fail_attempt(self, attempt, error: SafeError, summary=""): self.failures.append(error)


class _Artifacts:
    def __init__(self, values: dict) -> None:
        self.values, self.commits = values, []

    async def get_artifact_manifest(self, identifier): return self.values[identifier][0]
    async def read_content(self, identifier): return self.values[identifier][1]
    async def complete_with_outputs(self, run_id, attempt_id, outputs, **kwargs):
        self.commits.append((outputs, kwargs)); return (uuid4(),)


def test_executor_publishes_metric_report_with_all_input_artifact_lineage() -> None:
    expected = document(); expected_raw = expected.model_dump_json().encode()
    snapshot_id, expected_id, observed_id = uuid4(), uuid4(), uuid4()
    source = SourceArtifactRef(id=expected_id, artifact_type="canonical.document", content_digest=hashlib.sha256(expected_raw).hexdigest())
    reviewed = annotation().model_copy(update={"source": source})
    snapshot_raw = json.dumps({"taxonomy": {"schema_version": "SliceTaxonomy/v1", "dimensions": {"format": ["docx", "unknown"], "processing_class": ["native", "unknown"], "native_ocr": ["native", "unknown"], "structure": ["prose", "unknown"], "language": ["en", "unknown"], "question_class": ["lookup", "unknown"], "difficulty": ["low", "unknown"], "criticality": ["low", "unknown"]}}, "annotations": [reviewed.model_dump(mode="json")]}).encode()
    def item(identifier, kind, raw):
        return ArtifactManifest(id=identifier, artifact_type=kind, schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), summary="fixture", storage_locator="fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture.ingestion@1", configuration_digest="a" * 64)
    artifacts = _Artifacts({snapshot_id: (item(snapshot_id, "golden.dataset.snapshot", snapshot_raw), snapshot_raw), expected_id: (item(expected_id, "canonical.document", expected_raw), expected_raw), observed_id: (item(observed_id, "canonical.document", expected_raw), expected_raw)})
    async def exercise():
        await PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, _Runs(), artifacts).invoke(uuid4(), "metric.cer", "metric.ingestion.cer@1", {}, (snapshot_id, expected_id, observed_id))
    asyncio.run(exercise())
    stored = artifacts.commits[0][0][0][0]
    assert stored.artifact_type == "metric.report" and stored.parent_artifact_ids == (snapshot_id, expected_id, observed_id)


def _snapshot(labels: tuple[DocumentAnnotation, ...], dimensions=None) -> bytes:
    dimensions = dimensions or {key: list(values) for key, values in {
        "format": ("docx", "unknown"), "processing_class": ("native", "unknown"), "native_ocr": ("native", "unknown"),
        "structure": ("prose", "table", "unknown"), "language": ("en", "unknown"), "question_class": ("lookup", "unknown"),
        "difficulty": ("low", "unknown"), "criticality": ("low", "unknown"),
    }.items()}
    return json.dumps({"taxonomy": {"schema_version": "SliceTaxonomy/v1", "dimensions": dimensions}, "annotations": [item.model_dump(mode="json") for item in labels]}).encode()


def _execute_metric(metric_id: str, expected: CanonicalDocument, observed: CanonicalDocument | object, labels: tuple[DocumentAnnotation, ...], stage: str, dimensions=None):
    expected_raw = expected.model_dump_json().encode(); observed_raw = observed.model_dump_json().encode()
    snapshot_id, expected_id, observed_id = uuid4(), uuid4(), uuid4()
    source = SourceArtifactRef(id=expected_id, artifact_type="canonical.document", content_digest=hashlib.sha256(expected_raw).hexdigest())
    reviewed = tuple(item.model_copy(update={"source": source}) for item in labels)
    snapshot_raw = _snapshot(reviewed, dimensions)
    def item(identifier, kind, raw, producer):
        return ArtifactManifest(id=identifier, artifact_type=kind, schema_revision="v1", content_digest=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), summary="fixture", storage_locator="fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id=producer, configuration_digest="a" * 64)
    observed_kind = "chunk.set" if metric_id.endswith("evidence-preservation@1") else "canonical.document"
    values = {snapshot_id: (item(snapshot_id, "golden.dataset.snapshot", snapshot_raw, "dataset.fixture@1"), snapshot_raw), expected_id: (item(expected_id, "canonical.document", expected_raw, "expected.fixture@1"), expected_raw), observed_id: (item(observed_id, observed_kind, observed_raw, f"ingestion.{stage}@1"), observed_raw)}
    artifacts, runs = _Artifacts(values), _Runs()
    asyncio.run(PluginExecutor(bootstrap_registry(), {RunnerType.IN_PROCESS: InProcessRunner()}, runs, artifacts).invoke(uuid4(), f"metric.{stage}", metric_id, {}, (snapshot_id, expected_id, observed_id)))
    stored = artifacts.commits[0][0][0][0]
    return MetricReport.model_validate_json(artifacts.commits[0][0][0][1]), stored, values[observed_id][0]


@pytest.mark.parametrize(
    ("metric_id", "kind", "factory", "stage"),
    [
        ("metric.ingestion.cer@1", "text_span", document, "ocr"),
        ("metric.ingestion.element-f1@1", "element", document, "structure"),
        ("metric.ingestion.reading-order@1", "reading_order", document, "reading_order"),
        ("metric.ingestion.table-structure@1", "table", table_document, "table"),
        ("metric.ingestion.table-cell@1", "cell", table_document, "cells"),
        ("metric.ingestion.locator-accuracy@1", "locator", document, "locator"),
        ("metric.ingestion.evidence-preservation@1", "evidence_coverage", document, "chunking"),
    ],
)
def test_each_failure_family_executes_and_preserves_measured_artifact_lineage(metric_id, kind, factory, stage) -> None:
    expected = factory()
    labels = (metric_annotation(kind, expected),)
    if kind == "reading_order":
        labels = (*labels, annotation("reading_order").model_copy(update={"id": "ann_1123456789abcdef", "target": AnnotationTarget(kind="reading_order", element_id="elm_0000000000000003")}))
    observed = process(expected.model_dump_json().encode(), ChunkerConfig(strategy="fixed_window", max_tokens=64)) if kind == "evidence_coverage" else expected
    result, stored, observed_manifest = _execute_metric(metric_id, expected, observed, labels, stage)
    assert result.status is MetricStatus.VALUE and result.value == 1.0
    assert stored.parent_artifact_ids[-1] == result.observed_artifact_id
    assert observed_manifest.id == result.observed_artifact_id and observed_manifest.producing_plugin_id == f"ingestion.{stage}@1"


@pytest.mark.parametrize(
    ("metric_id", "labels", "expected_status"),
    [
        ("metric.ingestion.cer@1", (annotation("element"),), MetricStatus.NOT_APPLICABLE),
        ("metric.ingestion.reading-order@1", (annotation("reading_order"),), MetricStatus.INSUFFICIENT_LABELS),
    ],
)
def test_executor_emits_explicit_missing_data_states(metric_id, labels, expected_status) -> None:
    result, _, _ = _execute_metric(metric_id, document(), document(), labels, "missing")
    assert result.status is expected_status and result.value is None


def test_text_partial_and_failed_fixtures_remain_measured_values() -> None:
    expected = document()
    partial = expected.model_copy(update={"elements": tuple(item.model_copy(update={"text": "Inxxx"}) if item.id == "elm_0000000000000002" else item for item in expected.elements)})
    failed = expected.model_copy(update={"elements": tuple(item.model_copy(update={"text": "xxxxx"}) if item.id == "elm_0000000000000002" else item for item in expected.elements)})
    metric = IngestionMetricPlugin("metric.ingestion.cer@1")
    assert metric._score("text_span", (annotation(),), expected, partial)[0] == 0.4
    assert metric._score("text_span", (annotation(),), expected, failed) == (0.0, 0)


def test_cell_locator_and_evidence_partial_and_failed_fixtures_are_separate_values() -> None:
    expected = table_document(); table = expected.tables[0]
    cell_labels = (
        metric_annotation("cell", expected),
        metric_annotation("cell", expected).model_copy(update={"id": "ann_2123456789abcdef", "target": AnnotationTarget(kind="cell", table_id=table.id, cell_id=table.cells[1].id)}),
    )
    first_id = cell_labels[0].target.cell_id
    changed_cells = tuple(cell.model_copy(update={"text": "wrong"}) if cell.id == first_id else cell for cell in table.cells)
    partial_table = expected.model_copy(update={"tables": (table.model_copy(update={"cells": changed_cells}),)})
    cell_metric = IngestionMetricPlugin("metric.ingestion.table-cell@1")
    assert cell_metric._score("cell", cell_labels, expected, partial_table) == (0.5, 1)
    assert cell_metric._score("cell", cell_labels, expected, expected.model_copy(update={"tables": (table.model_copy(update={"cells": tuple(cell.model_copy(update={"text": "wrong"}) if cell.id in {item.target.cell_id for item in cell_labels} else cell for cell in table.cells)}),)})) == (0.0, 0)

    source = document()
    locator_labels = (
        metric_annotation("locator", source),
        metric_annotation("locator", source).model_copy(update={"id": "ann_3123456789abcdef", "target": AnnotationTarget(kind="locator", locator=source.elements[2].locator)}),
    )
    altered = source.model_copy(update={"elements": tuple(item.model_copy(update={"locator": item.locator.model_copy(update={"paragraph_index": 99})}) if item.id == source.elements[2].id else item for item in source.elements)})
    locator_metric = IngestionMetricPlugin("metric.ingestion.locator-accuracy@1")
    assert locator_metric._score("locator", locator_labels, source, altered) == (0.5, 1)

    chunks = process(source.model_dump_json().encode(), ChunkerConfig(strategy="fixed_window", max_tokens=64))
    evidence_labels = (
        metric_annotation("evidence_coverage", source),
        metric_annotation("evidence_coverage", source).model_copy(update={"id": "ann_4123456789abcdef", "target": AnnotationTarget(kind="evidence_coverage", element_id=source.elements[2].id)}),
    )
    stripped = chunks.model_copy(update={"chunks": tuple(chunk.model_copy(update={"citations": tuple(citation for citation in chunk.citations if citation.element_id != source.elements[2].id)}) for chunk in chunks.chunks)})
    assert IngestionMetricPlugin("metric.ingestion.evidence-preservation@1")._score("evidence_coverage", evidence_labels, source, stripped) == (0.5, 1)


def test_wer_element_order_and_table_structure_partial_and_zero_fixtures() -> None:
    source = document()
    wer_label = annotation().model_copy(update={"label": "Intro Detail", "target": AnnotationTarget(kind="text_span", element_id="elm_0000000000000002", start=0, end=12)})
    wer = IngestionMetricPlugin("metric.ingestion.wer@1")
    partial_text = source.model_copy(update={"elements": tuple(item.model_copy(update={"text": "Intro wrong"}) if item.id == wer_label.target.element_id else item for item in source.elements)})
    failed_text = source.model_copy(update={"elements": tuple(item.model_copy(update={"text": "wrong value"}) if item.id == wer_label.target.element_id else item for item in source.elements)})
    assert wer._score("text_span", (wer_label,), source, partial_text)[0] == 0.5
    assert wer._score("text_span", (wer_label,), source, failed_text) == (0.0, 0)

    element_labels = (metric_annotation("element", source), metric_annotation("element", source).model_copy(update={"id": "ann_5123456789abcdef", "target": AnnotationTarget(kind="element", element_id="elm_0000000000000003")}))
    f1 = IngestionMetricPlugin("metric.ingestion.element-f1@1")
    partial_elements = source.model_copy(update={"elements": tuple(item.model_copy(update={"kind": "figure"}) if item.id == "elm_0000000000000003" else item for item in source.elements)})
    failed_elements = source.model_copy(update={"elements": tuple(item.model_copy(update={"kind": "figure"}) if item.id in {"elm_0000000000000002", "elm_0000000000000003"} else item for item in source.elements)})
    assert f1._score("element", element_labels, source, partial_elements) == (0.5, 1)
    assert f1._score("element", element_labels, source, failed_elements) == (0.0, 0)

    order_labels = tuple(annotation("reading_order").model_copy(update={"id": f"ann_{index}123456789abcdef", "target": AnnotationTarget(kind="reading_order", element_id=identifier)}) for index, identifier in enumerate(("elm_0000000000000002", "elm_0000000000000003", "elm_0000000000000004"), 6))
    order = IngestionMetricPlugin("metric.ingestion.reading-order@1")
    partial_order = source.model_copy(update={"elements": tuple(item.model_copy(update={"reading_order": {"elm_0000000000000002": 1, "elm_0000000000000003": 3, "elm_0000000000000004": 2}.get(item.id, item.reading_order)}) for item in source.elements)})
    failed_order = source.model_copy(update={"elements": tuple(item.model_copy(update={"reading_order": {"elm_0000000000000002": 3, "elm_0000000000000003": 2, "elm_0000000000000004": 1}.get(item.id, item.reading_order)}) for item in source.elements)})
    assert order._score("reading_order", order_labels, source, partial_order)[0] == pytest.approx(2 / 3)
    assert order._score("reading_order", order_labels, source, failed_order) == (0.0, 0)

    expected = table_document(); table = expected.tables[0]
    extra = table.model_copy(update={"id": "tbl_0000000000000022", "locator": table.locator.model_copy(update={"range": "D2:F4"})})
    expected_two = expected.model_copy(update={"tables": (table, extra)})
    table_labels = (metric_annotation("table", expected), metric_annotation("table", expected).model_copy(update={"id": "ann_9123456789abcdef", "target": AnnotationTarget(kind="table", table_id=extra.id)}))
    structure = IngestionMetricPlugin("metric.ingestion.table-structure@1")
    assert structure._score("table", table_labels, expected_two, expected) == (0.5, 1)
    broken = expected.model_copy(update={"tables": (table.model_copy(update={"rows": table.rows + 1}),)})
    assert structure._score("table", table_labels, expected_two, broken) == (0.0, 0)


def test_fixture_metric_plugin_registers_and_generic_service_dispatches_without_branching() -> None:
    descriptor = PluginDescriptor(plugin_id="metric.ingestion.fixture@1", kind="metric", implementation_digest="f" * 64, runner=RunnerType.IN_PROCESS, configuration_schema=EmptyConfig.model_json_schema(), input_schemas=(("golden.dataset.snapshot", "v1"), ("canonical.document", "v1"), ("canonical.document", "v1")), output_schemas=(("metric.report", "v1"),), timeout_seconds=1)
    registry = bootstrap_registry()
    class FixtureMetric:
        async def invoke(self, context):
            snapshot, expected, observed = context.invocation.inputs
            payload = MetricReport(metric_id=descriptor.plugin_id, required_annotation_kinds=("text_span",), document_id="doc_0000000000000001", snapshot_artifact_id=snapshot.id, expected_artifact_id=expected.id, observed_artifact_id=observed.id, taxonomy_digest="d" * 64, slices=annotation().slices, status=MetricStatus.VALUE, value=1.0, elapsed_ms=0, labelled_count=1, matched_count=1)
            return PluginInvocationResult(outputs=(PluginOutput(artifact_type="metric.report", schema_revision="v1", content=metric_report_bytes(payload)),))
    registry.register(descriptor, FixtureMetric, EmptyConfig)
    expected = document(); raw = expected.model_dump_json().encode(); snapshot_id, expected_id, observed_id = uuid4(), uuid4(), uuid4()
    def item(identifier, kind, content): return ArtifactManifest(id=identifier, artifact_type=kind, schema_revision="v1", content_digest=hashlib.sha256(content).hexdigest(), byte_size=len(content), summary="fixture", storage_locator="fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture@1", configuration_digest="a" * 64)
    artifacts = _Artifacts({snapshot_id: (item(snapshot_id, "golden.dataset.snapshot", b"{}"), b"{}"), expected_id: (item(expected_id, "canonical.document", raw), raw), observed_id: (item(observed_id, "canonical.document", raw), raw)})
    output = asyncio.run(IngestionMetricService(PluginExecutor(registry, {RunnerType.IN_PROCESS: InProcessRunner()}, _Runs(), artifacts)).evaluate(uuid4(), "fixture.metric", descriptor.plugin_id, snapshot_id, expected_id, observed_id))
    assert output and registry.get(descriptor.plugin_id).descriptor == descriptor and artifacts.commits[0][0][0][0].parent_artifact_ids == (snapshot_id, expected_id, observed_id)


def test_aggregate_publication_uses_report_artifacts_as_trace_parents() -> None:
    reports = ((uuid4(), report(MetricStatus.VALUE, 1.0)), (uuid4(), report(MetricStatus.VALUE, 0.0, "doc_0000000000000002")))
    artifacts, runs = _Artifacts({}), _Runs()
    artifact_id, aggregate = asyncio.run(MetricAggregator().publish(uuid4(), "metric.aggregate", reports, "metric.ingestion.cer@1", {"language": "en"}, runs, artifacts))
    stored = artifacts.commits[0][0][0][0]
    assert artifact_id and aggregate.value == 0.5 and stored.artifact_type == "metric.aggregate" and stored.parent_artifact_ids == tuple(item[0] for item in sorted(reports, key=lambda item: str(item[0])))


def test_report_slices_are_validated_against_the_supplied_snapshot_taxonomy() -> None:
    expected = document(); custom_slices = {key: f"custom_{key}" for key in annotation().slices}
    dimensions = {key: [value] for key, value in custom_slices.items()}
    custom_label = annotation().model_copy(update={"slices": custom_slices})
    result, _, _ = _execute_metric("metric.ingestion.cer@1", expected, expected, (custom_label,), "custom", dimensions)
    assert result.slices == custom_slices
    invalid_label = custom_label.model_copy(update={"slices": {**custom_slices, "language": "not_declared"}})
    with pytest.raises(Exception):
        _execute_metric("metric.ingestion.cer@1", expected, expected, (invalid_label,), "custom", dimensions)
