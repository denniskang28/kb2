from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from kb2_runtime.canonical.contracts import CanonicalDocument
from kb2_runtime.evaluation.datasets.contracts import (
    AnnotationTarget, Answerability, CaseOrigin, CaseProvenance, DatasetContent,
    DocumentAnnotation, GoldenDataset, QueryCase, SourceArtifactRef, canonical_bytes,
)
from kb2_runtime.evaluation.datasets.service import DatasetService, DatasetValidationError
from kb2_runtime.evaluation.datasets.repository import DatasetRepository
from kb2_runtime.trace.contracts import ArtifactManifest
from kb2_runtime.chunking.contracts import ChunkerConfig
from kb2_runtime.chunking.processor import process
from kb2_runtime.evidence.contracts import ContextAssemblerConfig, ContextAssemblyRequest
from kb2_runtime.evidence.local import LocalContextAssembler
from kb2_runtime.evidence.serializer import evidence_set_bytes
from kb2_runtime.indexing.embedding import embed_chunk_set
from kb2_runtime.indexing.hybrid import build_index
from kb2_runtime.indexing.projection import project_search_documents
from kb2_runtime.retrieval.contracts import IndexArtifactBinding, RetrieverConfig, RetrieverRequest
from kb2_runtime.retrieval.local import TableRetriever


class _Artifacts:
    def __init__(self, values: dict) -> None:
        self.values = values

    async def get_artifact_manifest(self, identifier):
        raw, kind = self.values.get(identifier, (None, None))
        if raw is None: return None
        digest = hashlib.sha256(raw).hexdigest()
        return ArtifactManifest(id=identifier, artifact_type=kind, schema_revision="v1", content_digest=digest, byte_size=len(raw), summary="fixture", storage_locator="fixture", producing_run_id=uuid4(), producing_stage_attempt_id=uuid4(), producing_plugin_id="fixture@1", configuration_digest="a" * 64)

    async def read_content(self, identifier):
        return self.values[identifier][0]


def _document() -> tuple[bytes, CanonicalDocument]:
    raw = ("""{"schema_version":"CanonicalDocument/v1","document_id":"doc_0123456789abcdef","metadata":{},"provenance":{"source_artifact_id":"00000000-0000-0000-0000-000000000001","source_content_digest":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","adapter_id":"fixture@1"},"elements":[{"id":"elm_0123456789abcdef","kind":"paragraph","reading_order":0,"locator":{"kind":"html","path":"/body/p[1]","anchor":"p1"},"text":"golden text"}],"tables":[],"quality_signals":[]}""").encode()
    return raw, CanonicalDocument.model_validate_json(raw)


def _slices() -> dict[str, str]:
    return {"format":"html", "processing_class":"native", "native_ocr":"native", "structure":"prose", "language":"en", "question_class":"lookup", "difficulty":"low", "criticality":"low"}


def _annotation(identifier, document_ref) -> DocumentAnnotation:
    return DocumentAnnotation(id="ann_0123456789abcdef", source=document_ref, slices=_slices(), provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), target=AnnotationTarget(kind="text_span", element_id="elm_0123456789abcdef", start=0, end=6), label="relevant text")


def test_annotation_requires_explicit_review_and_edits_clear_eligibility() -> None:
    async def exercise():
        raw, _ = _document(); identifier = uuid4()
        ref = SourceArtifactRef(id=identifier, artifact_type="canonical.document", content_digest=hashlib.sha256(raw).hexdigest())
        content = DatasetContent(annotations=(_annotation(identifier, ref),))
        service = DatasetService(_Artifacts({identifier: (raw, "canonical.document")}))
        assert await service.validate(content) == {"ann_0123456789abcdef": ()}
        reviewed = await service.mark_reviewed(content, "ann_0123456789abcdef", "reviewer")
        assert reviewed.annotations[0].reviews[-1].operation == "mark_reviewed"
        edited = reviewed.model_copy(update={"annotations": (reviewed.annotations[0].model_copy(update={"label": "changed", "reviews": ()}),)})
        assert not service._is_reviewed(edited.annotations[0])
    asyncio.run(exercise())


def test_invalid_locator_unknown_slice_and_contradictory_answerability_are_blocking() -> None:
    async def exercise():
        raw, _ = _document(); identifier = uuid4(); digest = hashlib.sha256(raw).hexdigest()
        ref = SourceArtifactRef(id=identifier, artifact_type="canonical.document", content_digest=digest)
        broken = _annotation(identifier, ref).model_copy(update={"target": AnnotationTarget(kind="element", element_id="elm_ffffffffffffffff"), "slices": {**_slices(), "format": "made_up"}})
        query = QueryCase(id="qcase_0123456789abcdef", source=ref, slices=_slices(), provenance=CaseProvenance(origin=CaseOrigin.GENERATED, operation="generated", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), question="What?", answerability=Answerability.AMBIGUOUS, expected_facts=("a fact",))
        report = await DatasetService(_Artifacts({identifier: (raw, "canonical.document")})).validate(DatasetContent(annotations=(broken,), query_cases=(query,)))
        assert "LOCATOR_INVALID" in report[broken.id] and "UNKNOWN_SLICE" in report[broken.id]
        assert "ANSWERABILITY_CONTRADICTORY" in report[query.id]
    asyncio.run(exercise())


def test_canonical_dataset_bytes_are_stable() -> None:
    content = DatasetContent()
    assert canonical_bytes(content) == DatasetService.export(content)
    assert DatasetService.import_content(DatasetService.export(content)) == content


def test_snapshot_replay_keeps_prior_bytes_immutable() -> None:
    class Catalog:
        def __init__(self, dataset_id, values): self.dataset_id, self.values = dataset_id, values
        async def get(self, dataset_id, revision): return self.values[revision]
    class Runs:
        def __init__(self): self.plans = []; self.finished = []
        async def create_run(self, kind, plan): self.plans.append(plan); return uuid4()
        async def start_attempt(self, run, key, parents): return uuid4(), 1
        async def finish_run(self, run, success): self.finished.append((run, success))

    class Publisher:
        def __init__(self): self.outputs = []
        async def complete_with_outputs(self, run, attempt, outputs, **kwargs):
            self.outputs.extend(outputs); return (uuid4(),)

    async def exercise():
        raw, _ = _document(); identifier = uuid4(); ref = SourceArtifactRef(id=identifier, artifact_type="canonical.document", content_digest=hashlib.sha256(raw).hexdigest())
        service = DatasetService(_Artifacts({identifier: (raw, "canonical.document")})); runs, publisher = Runs(), Publisher()
        draft = DatasetContent(annotations=(_annotation(identifier, ref),))
        reviewed = await service.mark_reviewed(draft, "ann_0123456789abcdef", "reviewer")
        dataset_id = uuid4()
        def stored(number, content):
            return GoldenDataset(id=dataset_id, revision_id=uuid4(), revision=number, content=content, content_digest=hashlib.sha256(canonical_bytes(content)).hexdigest(), operation="create" if number == 1 else "edit", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        catalog = Catalog(dataset_id, {1: stored(1, reviewed)})
        _, snapshot_a = await service.create_snapshot(catalog, dataset_id, 1, runs, publisher)
        bytes_a = publisher.outputs[0][1]
        changed_draft = reviewed.model_copy(update={"annotations": (reviewed.annotations[0].model_copy(update={"label": "replacement", "reviews": ()}),)})
        changed = await service.mark_reviewed(changed_draft, "ann_0123456789abcdef", "reviewer")
        catalog.values[2] = stored(2, changed)
        _, snapshot_b = await service.create_snapshot(catalog, dataset_id, 2, runs, publisher)
        assert snapshot_a != snapshot_b and bytes_a != publisher.outputs[1][1] and publisher.outputs[0][1] == bytes_a
        assert len(runs.plans) == 2 and all(done for _, done in runs.finished)
    asyncio.run(exercise())


def test_persisted_snapshot_rejects_draft_revision_until_review_event_is_recorded() -> None:
    class Catalog:
        def __init__(self, value): self.value, self.events = value, []
        async def get(self, dataset_id, revision): return self.value
        async def record_review(self, dataset_id, revision, case_id, review):
            self.events.append(review)
            case = self.value.content.annotations[0].model_copy(update={"reviews": (review,)})
            self.value = self.value.model_copy(update={"content": self.value.content.model_copy(update={"annotations": (case,)})})

    class Runs:
        async def create_run(self, *_): return uuid4()
        async def start_attempt(self, *_): return uuid4(), 1
        async def finish_run(self, *_): pass

    class Publisher:
        async def complete_with_outputs(self, *_args, **_kwargs): return (uuid4(),)

    async def exercise():
        raw, _ = _document(); source_id, dataset_id = uuid4(), uuid4()
        ref = SourceArtifactRef(id=source_id, artifact_type="canonical.document", content_digest=hashlib.sha256(raw).hexdigest())
        content = DatasetContent(annotations=(_annotation(source_id, ref),))
        catalog = Catalog(GoldenDataset(id=dataset_id, revision_id=uuid4(), revision=1, content=content, content_digest=hashlib.sha256(canonical_bytes(content)).hexdigest(), operation="create", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        service = DatasetService(_Artifacts({source_id: (raw, "canonical.document")}))
        with pytest.raises(DatasetValidationError):
            await service.create_snapshot(catalog, dataset_id, 1, Runs(), Publisher())
        await service.mark_persisted_review(catalog, dataset_id, 1, "ann_0123456789abcdef", "reviewer")
        assert len(catalog.events) == 1
        await service.create_snapshot(catalog, dataset_id, 1, Runs(), Publisher())
    asyncio.run(exercise())


def test_create_and_generated_cases_cannot_replay_review_payloads() -> None:
    async def exercise():
        raw, _ = _document(); identifier = uuid4()
        ref = SourceArtifactRef(id=identifier, artifact_type="canonical.document", content_digest=hashlib.sha256(raw).hexdigest())
        service = DatasetService(_Artifacts({identifier: (raw, "canonical.document")}))
        reviewed = await service.mark_reviewed(DatasetContent(annotations=(_annotation(identifier, ref),)), "ann_0123456789abcdef", "reviewer")
        assert DatasetRepository._initial_reviews(reviewed, "create").annotations[0].reviews == ()
        generated = reviewed.model_copy(update={"annotations": (reviewed.annotations[0].model_copy(update={"provenance": CaseProvenance(origin=CaseOrigin.GENERATED, operation="generated", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))}),)})
        assert DatasetRepository._initial_reviews(generated, "import").annotations[0].reviews == ()
        assert DatasetRepository._initial_reviews(reviewed, "import").annotations[0].reviews
    asyncio.run(exercise())


def test_repository_rejects_unknown_revision_operations() -> None:
    with pytest.raises(ValueError):
        DatasetRepository._validate_operation("replace", ("create", "import"))


def test_fixture_catalog_declares_all_required_review_and_case_states() -> None:
    fixture = json.loads((Path(__file__).parents[1] / "fixtures" / "golden_datasets" / "cases.json").read_text())
    assert set(fixture["review_states"]) == {"reviewed", "draft", "generated", "invalid"}
    assert set(fixture["answerability"]) == {"answerable", "ambiguous", "unanswerable"}
    assert set(fixture["annotation_targets"]) >= {"text_span", "element", "table", "cell"}


def test_valid_answerable_evidence_and_structural_annotations_round_trip() -> None:
    async def exercise():
        table_raw = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "table-heavy-canonical.json").read_bytes()
        hierarchy_raw = (Path(__file__).parents[1] / "fixtures" / "ingestion" / "long-hierarchy-canonical.json").read_bytes()
        table_id, hierarchy_id, evidence_artifact_id = uuid4(), uuid4(), uuid4()
        table_ref = SourceArtifactRef(id=table_id, artifact_type="canonical.document", content_digest=hashlib.sha256(table_raw).hexdigest())
        hierarchy_ref = SourceArtifactRef(id=hierarchy_id, artifact_type="canonical.document", content_digest=hashlib.sha256(hierarchy_raw).hexdigest())
        chunks = process(table_raw, ChunkerConfig(strategy="table", max_tokens=64))
        index = await build_index(project_search_documents(chunks, embed_chunk_set(chunks)))
        binding = IndexArtifactBinding(id=uuid4(), content_digest="a" * 64)
        candidates = TableRetriever().retrieve(RetrieverRequest(query="revenue", index=index, index_binding=binding, contributor_id="table", configuration=RetrieverConfig(limit=8), configuration_digest="b" * 64, plugin_id="retriever.table@1", implementation_digest="c" * 64))
        evidence = LocalContextAssembler().assemble(ContextAssemblyRequest(candidates=candidates, index=index, index_binding=binding, configuration=ContextAssemblerConfig(structural_rule="table", max_items=8, max_tokens=2048, max_excerpt_chars=64), configuration_digest="e" * 64, plugin_id="context.from-retrieval@1", implementation_digest="f" * 64))
        evidence_raw = evidence_set_bytes(evidence)
        evidence_ref = SourceArtifactRef(id=evidence_artifact_id, artifact_type="evidence.set", content_digest=hashlib.sha256(evidence_raw).hexdigest())
        slices = _slices(); slices["question_class"] = "table"
        answerable = QueryCase(id="qcase_0123456789abcdea", source=table_ref, slices=slices, provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), question="What is revenue?", answerability=Answerability.ANSWERABLE, expected_facts=("Revenue is present",), evidence=evidence_ref, relevant_evidence_ids=(evidence.items[0].evidence_id,), required_citation_keys=(evidence.items[0].citation_key,))
        neutral = _slices(); neutral["question_class"] = "ambiguous"
        ambiguous = QueryCase(id="qcase_0123456789abcdeb", source=table_ref, slices=neutral, provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), question="Which unspecified value?", answerability=Answerability.AMBIGUOUS)
        neutral_unanswerable = _slices(); neutral_unanswerable["question_class"] = "unanswerable"
        unanswerable = QueryCase(id="qcase_0123456789abcdec", source=table_ref, slices=neutral_unanswerable, provenance=CaseProvenance(origin=CaseOrigin.MANUAL, operation="create", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), question="What is absent?", answerability=Answerability.UNANSWERABLE, forbidden_facts=("An unsupported value",))
        hierarchy = _annotation(hierarchy_id, hierarchy_ref).model_copy(update={"id": "ann_0123456789abcdea", "target": AnnotationTarget(kind="element", element_id="elm_0000000000000003")})
        table = _annotation(table_id, table_ref).model_copy(update={"id": "ann_0123456789abcdeb", "target": AnnotationTarget(kind="table", table_id="tbl_0000000000000021")})
        cell = _annotation(table_id, table_ref).model_copy(update={"id": "ann_0123456789abcdec", "target": AnnotationTarget(kind="cell", table_id="tbl_0000000000000021", cell_id="cel_0000000000000024")})
        artifacts = _Artifacts({table_id: (table_raw, "canonical.document"), hierarchy_id: (hierarchy_raw, "canonical.document"), evidence_artifact_id: (evidence_raw, "evidence.set")})
        report = await DatasetService(artifacts).validate(DatasetContent(annotations=(hierarchy, table, cell), query_cases=(answerable, ambiguous, unanswerable)))
        assert all(not errors for errors in report.values())
    asyncio.run(exercise())
