from __future__ import annotations

import unicodedata
import hashlib

from kb2_runtime.canonical.contracts import CanonicalDocument
from kb2_runtime.canonical.serializer import locator_key
from kb2_runtime.chunking.contracts import ChunkSet
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput
from kb2_runtime.evaluation.datasets.contracts import DatasetContent, DocumentAnnotation, canonical_bytes

from .contracts import MetricReport, MetricStatus, metric_report_bytes

METRICS = {
    "metric.ingestion.cer@1": ("text_span",), "metric.ingestion.wer@1": ("text_span",),
    "metric.ingestion.element-f1@1": ("element",), "metric.ingestion.reading-order@1": ("reading_order",),
    "metric.ingestion.table-structure@1": ("table",), "metric.ingestion.table-cell@1": ("cell",),
    "metric.ingestion.locator-accuracy@1": ("locator",), "metric.ingestion.evidence-preservation@1": ("evidence_coverage",),
}

def _norm(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())

def _distance(left: list[str], right: list[str]) -> int:
    row = list(range(len(right) + 1))
    for i, value in enumerate(left, 1):
        next_row = [i]
        for j, candidate in enumerate(right, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (value != candidate)))
        row = next_row
    return row[-1]

class IngestionMetricPlugin:
    def __init__(self, metric_id: str) -> None: self.metric_id = metric_id

    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        snapshot, expected_input, observed_input = tuple(
            [await context.input(item.id) for item in context.invocation.inputs]
        )
        try:
            raw = __import__("json").loads(snapshot.content)
            content = DatasetContent.model_validate({"taxonomy": raw["taxonomy"], "annotations": raw["annotations"], "query_cases": raw.get("query_cases", [])})
            expected = CanonicalDocument.model_validate_json(expected_input.content)
            observed = ChunkSet.model_validate_json(observed_input.content) if self.metric_id.endswith("evidence-preservation@1") else CanonicalDocument.model_validate_json(observed_input.content)
        except Exception as exc:
            raise ValueError("metric inputs are invalid") from exc
        kind = METRICS[self.metric_id][0]
        sources = tuple(item.source for item in content.annotations)
        if not any(source.id == expected_input.reference.id for source in sources):
            raise ValueError("expected artifact is absent from snapshot")
        if any(source.id == expected_input.reference.id and source.content_digest != expected_input.reference.content_digest for source in sources):
            raise ValueError("expected artifact does not match reviewed source")
        if any(
            set(item.slices) != set(content.taxonomy.dimensions)
            or any(value not in content.taxonomy.dimensions[key] for key, value in item.slices.items())
            for item in content.annotations
        ):
            raise ValueError("snapshot annotation slices are outside its taxonomy")
        labels = tuple(item for item in content.annotations if item.source.id == expected_input.reference.id and item.target.kind == kind)
        if not labels and any(
            item.target.kind == kind and item.source.content_digest == expected_input.reference.content_digest
            for item in content.annotations
        ):
            raise ValueError("expected artifact identifier does not match reviewed source")
        if labels and any(item.slices != labels[0].slices for item in labels):
            raise ValueError("document annotations have conflicting slices")
        if not labels:
            status, value, matched = MetricStatus.NOT_APPLICABLE, None, 0
        elif expected.document_id != (observed.document_id if isinstance(observed, (CanonicalDocument, ChunkSet)) else None):
            raise ValueError("observed document identity differs")
        elif kind == "reading_order" and len(labels) < 2:
            status, value, matched = MetricStatus.INSUFFICIENT_LABELS, None, 0
        else:
            value, matched = self._score(kind, labels, expected, observed)
            status = MetricStatus.VALUE
        slices = labels[0].slices if labels else {key: "unknown" for key in content.taxonomy.dimensions}
        report = MetricReport(metric_id=self.metric_id, required_annotation_kinds=METRICS[self.metric_id], document_id=expected.document_id,
            snapshot_artifact_id=snapshot.reference.id, expected_artifact_id=expected_input.reference.id, observed_artifact_id=observed_input.reference.id,
            taxonomy_digest=hashlib.sha256(canonical_bytes(content.taxonomy)).hexdigest(), slices=slices, status=status, value=value, elapsed_ms=0, labelled_count=len(labels), matched_count=matched)
        return PluginInvocationResult(outputs=(PluginOutput(artifact_type="metric.report", schema_revision="v1", content=metric_report_bytes(report), summary="ingestion metric report"),))

    def _score(self, kind: str, labels: tuple[DocumentAnnotation, ...], expected: CanonicalDocument, observed: CanonicalDocument | ChunkSet) -> tuple[float, int]:
        elements = {item.id: item for item in expected.elements}; observed_elements = {item.id: item for item in observed.elements} if isinstance(observed, CanonicalDocument) else {}
        if kind in {"text_span"}:
            distances = totals = 0
            for item in labels:
                actual = observed_elements.get(item.target.element_id)
                text = actual.text if actual and actual.text is not None else ""
                region = text[item.target.start:item.target.end]
                left = list(_norm(item.label)) if self.metric_id.endswith("cer@1") else _norm(item.label).split()
                right = list(_norm(region)) if self.metric_id.endswith("cer@1") else _norm(region).split()
                totals += max(len(left), 1); distances += _distance(left, right)
            return max(0.0, 1 - distances / totals), len(labels) if distances == 0 else 0
        if kind == "element":
            expected_pairs = {(locator_key(elements[item.target.element_id].locator), elements[item.target.element_id].kind) for item in labels}
            labelled_locators = {locator for locator, _ in expected_pairs}
            observed_pairs = {(locator_key(item.locator), item.kind) for item in observed_elements.values() if locator_key(item.locator) in labelled_locators}
            matched = len(expected_pairs & observed_pairs)
            denominator = len(expected_pairs) + len(observed_pairs)
            return (2 * matched / denominator if denominator else 0.0), matched
        if kind == "reading_order":
            expected_by_id = {item.id: item for item in expected.elements}
            observed_by_pair = {(locator_key(item.locator), item.kind): item for item in observed_elements.values()}
            pairs = []
            for annotation in labels:
                target = expected_by_id[annotation.target.element_id]
                observed_target = observed_by_pair.get((locator_key(target.locator), target.kind))
                if observed_target is not None:
                    pairs.append((target.reading_order, observed_target.reading_order))
            pairs.sort()
            matched = 0; total = len(labels) * (len(labels) - 1) // 2
            for index, (_, left_order) in enumerate(pairs):
                for _, right_order in pairs[index + 1:]:
                    if left_order < right_order: matched += 1
            return matched / total, matched
        if kind == "table":
            expected_tables = {item.id: item for item in expected.tables}; observed_tables = {locator_key(item.locator): item for item in observed.tables}  # type: ignore[union-attr]
            matched = sum(1 for item in labels if (table := expected_tables.get(item.target.table_id)) and (candidate := observed_tables.get(locator_key(table.locator))) and (table.rows, table.columns, [(x.row,x.column,x.row_span,x.column_span,x.is_header) for x in table.cells]) == (candidate.rows,candidate.columns,[(x.row,x.column,x.row_span,x.column_span,x.is_header) for x in candidate.cells]))
            return matched / len(labels), matched
        if kind == "cell":
            expected_tables = {item.id: item for item in expected.tables}; observed_tables = {locator_key(item.locator): item for item in observed.tables}  # type: ignore[union-attr]
            matched = 0
            for item in labels:
                table = expected_tables[item.target.table_id]; cell = next(x for x in table.cells if x.id == item.target.cell_id); candidate = observed_tables.get(locator_key(table.locator))
                if candidate and any((x.row,x.column,x.row_span,x.column_span,x.is_header,_norm(x.text)) == (cell.row,cell.column,cell.row_span,cell.column_span,cell.is_header,_norm(cell.text)) for x in candidate.cells): matched += 1
            return matched / len(labels), matched
        if kind == "locator":
            locators = {locator_key(item.locator) for item in observed.elements} | {locator_key(item.locator) for item in observed.tables}  # type: ignore[union-attr]
            matched = sum(locator_key(item.target.locator) in locators for item in labels); return matched / len(labels), matched
        citations = {locator_key(citation.locator) for chunk in observed.chunks for citation in chunk.citations}  # type: ignore[union-attr]
        matched = sum(locator_key(elements[item.target.element_id].locator) in citations for item in labels)
        return matched / len(labels), matched
