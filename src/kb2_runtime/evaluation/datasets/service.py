from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from kb2_runtime.canonical.contracts import CanonicalDocument
from kb2_runtime.evidence.contracts import EvidenceSet
from kb2_runtime.trace.contracts import ArtifactInput, ArtifactManifest, EngineKind
from kb2_runtime.trace.service import ArtifactService, RunService, plan_digest

from .contracts import (Answerability, CaseOrigin, DatasetCase, DatasetContent, DocumentAnnotation,
                        QueryCase, ReviewEvent, SourceArtifactRef, canonical_bytes, content_digest)
from .repository import DatasetRepository


class ArtifactReader(Protocol):
    async def get_artifact_manifest(self, artifact_id: UUID) -> ArtifactManifest | None: ...
    async def read_content(self, artifact_id: UUID) -> bytes: ...


class DatasetValidationError(ValueError):
    pass


class DatasetService:
    """Pure validation plus immutable snapshot publication over trace Artifacts."""
    def __init__(self, artifacts: ArtifactReader) -> None:
        self.artifacts = artifacts

    @staticmethod
    def export(content: DatasetContent) -> bytes:
        """Canonical portable form; it contains no source bodies or credentials."""
        return canonical_bytes(content)

    @staticmethod
    def import_content(payload: bytes) -> DatasetContent:
        """Imports can retain only a verifiable explicit review event."""
        try:
            content = DatasetContent.model_validate_json(payload)
        except Exception as exc:
            raise DatasetValidationError("dataset import is invalid") from exc
        def imported(case: DatasetCase) -> DatasetCase:
            if DatasetService._is_reviewed(case):
                return case
            return case.model_copy(update={"reviews": ()})
        return content.model_copy(update={
            "annotations": tuple(imported(case) for case in content.annotations),
            "query_cases": tuple(imported(case) for case in content.query_cases),
        })

    @staticmethod
    def edit_as_draft(content: DatasetContent) -> DatasetContent:
        """Authoring changes must pass through explicit review again."""
        return content.model_copy(update={
            "annotations": tuple(case.model_copy(update={"reviews": ()}) for case in content.annotations),
            "query_cases": tuple(case.model_copy(update={"reviews": ()}) for case in content.query_cases),
        })

    async def validate(self, content: DatasetContent) -> dict[str, tuple[str, ...]]:
        report: dict[str, tuple[str, ...]] = {}
        for case in (*content.annotations, *content.query_cases):
            errors = list(self._slice_errors(case, content))
            if isinstance(case, DocumentAnnotation):
                errors.extend(await self._annotation_errors(case))
            else:
                errors.extend(await self._query_errors(case))
            report[case.id] = tuple(sorted(set(errors)))
        return report

    async def mark_reviewed(self, content: DatasetContent, case_id: str, reviewer: str, *, now: datetime | None = None) -> DatasetContent:
        report = await self.validate(content)
        if report.get(case_id) or not reviewer:
            raise DatasetValidationError("case is not eligible for review")
        moment = now or datetime.now(timezone.utc)
        def review(case: DatasetCase) -> DatasetCase:
            if case.id != case_id:
                return case
            digest = hashlib.sha256(canonical_bytes(case.model_copy(update={"reviews": ()}))).hexdigest()
            return case.model_copy(update={"reviews": (*case.reviews, ReviewEvent(reviewer=reviewer, reviewed_at=moment, content_digest=digest))})
        return content.model_copy(update={"annotations": tuple(review(item) for item in content.annotations), "query_cases": tuple(review(item) for item in content.query_cases)})

    async def mark_persisted_review(self, repository: DatasetRepository, dataset_id: UUID, revision: int, case_id: str, reviewer: str, *, now: datetime | None = None) -> DatasetContent:
        """The review fact is append-only and bound to the stored revision content."""
        stored = await repository.get(dataset_id, revision)
        reviewed = await self.mark_reviewed(stored.content, case_id, reviewer, now=now)
        target = next((item for item in (*reviewed.annotations, *reviewed.query_cases) if item.id == case_id), None)
        if target is None or not target.reviews:
            raise DatasetValidationError("review event was not recorded")
        await repository.record_review(dataset_id, revision, case_id, target.reviews[-1])
        return (await repository.get(dataset_id, revision)).content

    async def create_snapshot(self, repository: DatasetRepository, dataset_id: UUID, revision: int, runs: RunService, artifact_service: ArtifactService) -> tuple[UUID, UUID]:
        """Publish only the exact persisted revision, never detached authoring data."""
        stored = await repository.get(dataset_id, revision)
        content = stored.content
        report = await self.validate(content)
        cases = (*content.annotations, *content.query_cases)
        if not cases or any(report[item.id] or not self._is_reviewed(item) for item in cases):
            raise DatasetValidationError("dataset is not snapshot eligible")
        parents = tuple(sorted({item.source.id for item in cases} | {item.evidence.id for item in content.query_cases if item.evidence}, key=str))
        if len(parents) > 64:
            raise DatasetValidationError("dataset source limit exceeded")
        payload: dict[str, Any] = {"schema_version": "GoldenDatasetSnapshot/v1", "dataset_id": str(dataset_id), "dataset_revision_id": str(stored.revision_id), "revision": revision, "content_digest": content_digest(content), "taxonomy": content.taxonomy.model_dump(mode="json"), "annotations": [x.model_dump(mode="json") for x in content.annotations], "query_cases": [x.model_dump(mode="json") for x in content.query_cases], "sources": [str(x) for x in parents]}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        digest = hashlib.sha256(raw).hexdigest()
        plan = {"dataset_id": str(dataset_id), "dataset_revision": revision, "dataset_digest": content_digest(content), "taxonomy_digest": hashlib.sha256(canonical_bytes(content.taxonomy)).hexdigest()}
        run_id = await runs.create_run(EngineKind.EVALUATION, plan)
        attempt_id, _ = await runs.start_attempt(run_id, "dataset.snapshot", parents)
        manifest = ArtifactInput(artifact_type="golden.dataset.snapshot", schema_revision="v1", content_digest=digest, byte_size=len(raw), producing_plugin_id="evaluation.dataset-snapshot@1", configuration_digest=plan_digest(plan), parent_artifact_ids=parents, summary="immutable golden dataset snapshot")
        artifact_id = (await artifact_service.complete_with_outputs(run_id, attempt_id, ((manifest, raw),), summary="dataset snapshot"))[0]
        await runs.finish_run(run_id, True)
        return run_id, artifact_id

    def _slice_errors(self, case: DatasetCase, content: DatasetContent) -> tuple[str, ...]:
        return tuple("UNKNOWN_SLICE" for dimension, value in case.slices.items() if dimension not in content.taxonomy.dimensions or value not in content.taxonomy.dimensions[dimension]) + (("SLICE_SET_INVALID",) if set(case.slices) != set(content.taxonomy.dimensions) else ())

    async def _load(self, ref: SourceArtifactRef, expected_type: str) -> object | None:
        try:
            manifest = await self.artifacts.get_artifact_manifest(ref.id)
            if not manifest or manifest.artifact_type != expected_type or manifest.schema_revision != ref.schema_revision or manifest.content_digest != ref.content_digest:
                return None
            raw = await self.artifacts.read_content(ref.id)
            if hashlib.sha256(raw).hexdigest() != ref.content_digest:
                return None
            return CanonicalDocument.model_validate_json(raw) if expected_type == "canonical.document" else EvidenceSet.model_validate_json(raw)
        except Exception:
            return None

    async def _annotation_errors(self, case: DocumentAnnotation) -> list[str]:
        document = await self._load(case.source, "canonical.document")
        if not isinstance(document, CanonicalDocument): return ["DOCUMENT_REFERENCE_BROKEN"]
        target = case.target; elements = {x.id: x for x in document.elements}; tables = {x.id: x for x in document.tables}
        if target.element_id and target.element_id not in elements: return ["LOCATOR_INVALID"]
        if target.table_id and target.table_id not in tables: return ["LOCATOR_INVALID"]
        if target.cell_id and (not target.table_id or target.cell_id not in {x.id for x in tables[target.table_id].cells}): return ["LOCATOR_INVALID"]
        if target.kind == "text_span":
            text = elements[target.element_id].text if target.element_id else None
            if text is None or target.end is None or target.end > len(text): return ["LOCATOR_INVALID"]
        if target.locator and target.locator not in [x.locator for x in document.elements] + [x.locator for x in document.tables]: return ["LOCATOR_INVALID"]
        return []

    async def _query_errors(self, case: QueryCase) -> list[str]:
        errors: list[str] = []
        document = await self._load(case.source, "canonical.document")
        if not isinstance(document, CanonicalDocument):
            errors.append("DOCUMENT_REFERENCE_BROKEN")
        normalized = lambda values: [" ".join(item.split()).casefold() for item in values]
        expected, forbidden = normalized(case.expected_facts), normalized(case.forbidden_facts)
        if len(expected) != len(set(expected)) or len(forbidden) != len(set(forbidden)) or set(expected) & set(forbidden): errors.append("FACTS_INVALID")
        empty_only = any((case.expected_facts, case.deterministic_answer, case.relevant_evidence_ids, case.required_citation_keys))
        if case.answerability is Answerability.ANSWERABLE and (not case.expected_facts or not case.evidence or not case.relevant_evidence_ids or not case.required_citation_keys): errors.append("ANSWERABILITY_CONTRADICTORY")
        if case.answerability is not Answerability.ANSWERABLE and empty_only: errors.append("ANSWERABILITY_CONTRADICTORY")
        if case.evidence:
            evidence = await self._load(case.evidence, "evidence.set")
            if not isinstance(evidence, EvidenceSet): errors.append("EVIDENCE_REFERENCE_BROKEN")
            else:
                ids = {x.evidence_id for x in evidence.items}
                relevant_citations = {x.citation_key for x in evidence.items if x.evidence_id in case.relevant_evidence_ids}
                if (not isinstance(document, CanonicalDocument) or evidence.document_id != document.document_id
                    or not set(case.relevant_evidence_ids) <= ids or not set(case.required_citation_keys) <= relevant_citations
                    or len(case.relevant_evidence_ids) != len(set(case.relevant_evidence_ids))
                    or len(case.required_citation_keys) != len(set(case.required_citation_keys))): errors.append("EVIDENCE_REFERENCE_BROKEN")
        elif case.relevant_evidence_ids or case.required_citation_keys: errors.append("EVIDENCE_REFERENCE_BROKEN")
        return errors

    @staticmethod
    def _is_reviewed(case: DatasetCase) -> bool:
        bare = case.model_copy(update={"reviews": ()})
        digest = hashlib.sha256(canonical_bytes(bare)).hexdigest()
        return bool(case.reviews) and case.reviews[-1].content_digest == digest
