from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb2_runtime.canonical.contracts import Locator, StableId

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
CaseId = Annotated[str, Field(pattern=r"^(?:ann|qcase)_[a-f0-9]{16,64}$")]


class DatasetContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseOrigin(StrEnum):
    MANUAL = "manual"
    GENERATED = "generated"
    IMPORTED = "imported"


class Answerability(StrEnum):
    ANSWERABLE = "answerable"
    AMBIGUOUS = "ambiguous"
    UNANSWERABLE = "unanswerable"


class SourceArtifactRef(DatasetContract):
    id: UUID
    content_digest: Digest
    schema_revision: Literal["v1"] = "v1"
    artifact_type: Literal["canonical.document", "evidence.set"]


class SliceTaxonomy(DatasetContract):
    schema_version: Literal["SliceTaxonomy/v1"] = "SliceTaxonomy/v1"
    dimensions: dict[Annotated[str, Field(pattern=r"^[a-z][a-z_]{1,31}$")], tuple[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")], ...]]

    @model_validator(mode="after")
    def closed_values(self) -> "SliceTaxonomy":
        required = {"format", "processing_class", "native_ocr", "structure", "language", "question_class", "difficulty", "criticality"}
        if set(self.dimensions) != required or any(not values or len(values) != len(set(values)) for values in self.dimensions.values()):
            raise ValueError("taxonomy dimensions or values are invalid")
        return self


DEFAULT_TAXONOMY = SliceTaxonomy(dimensions={
    "format": ("pdf", "docx", "xlsx", "html", "unknown"),
    "processing_class": ("native", "ocr", "mixed", "unknown"),
    "native_ocr": ("native", "ocr", "mixed", "unknown"),
    "structure": ("prose", "hierarchy", "table", "layout_rich", "unknown"),
    "language": ("en", "zh", "multilingual", "unknown"),
    "question_class": ("lookup", "multi_evidence", "table", "comparison", "summary", "ambiguous", "unanswerable", "unknown"),
    "difficulty": ("low", "medium", "high", "unknown"),
    "criticality": ("low", "medium", "high", "unknown"),
})


class AnnotationTarget(DatasetContract):
    kind: Literal["text_span", "element", "reading_order", "table", "cell", "locator", "evidence_coverage"]
    element_id: StableId | None = None
    table_id: StableId | None = None
    cell_id: StableId | None = None
    locator: Locator | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def target_shape(self) -> "AnnotationTarget":
        if self.kind == "text_span" and (not self.element_id or self.start is None or self.end is None or self.end <= self.start):
            raise ValueError("text span requires bounded element range")
        if self.kind in {"element", "reading_order", "evidence_coverage"} and not self.element_id:
            raise ValueError("element target is required")
        if self.kind == "table" and not self.table_id:
            raise ValueError("table target is required")
        if self.kind == "cell" and (not self.table_id or not self.cell_id):
            raise ValueError("cell target is required")
        if self.kind == "locator" and not self.locator:
            raise ValueError("locator target is required")
        return self


class ReviewEvent(DatasetContract):
    operation: Literal["mark_reviewed"] = "mark_reviewed"
    reviewer: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.@-]{1,64}$")]
    reviewed_at: datetime
    content_digest: Digest


class CaseProvenance(DatasetContract):
    origin: CaseOrigin
    operation: Literal["create", "edit", "import", "generated"]
    created_at: datetime


class DatasetCase(DatasetContract):
    id: CaseId
    source: SourceArtifactRef
    slices: dict[str, str] = Field(min_length=8, max_length=8)
    provenance: CaseProvenance
    reviews: tuple[ReviewEvent, ...] = Field(default_factory=tuple, max_length=32)


class DocumentAnnotation(DatasetCase):
    source: SourceArtifactRef
    target: AnnotationTarget
    label: Annotated[str, Field(min_length=1, max_length=1024)]


class QueryCase(DatasetCase):
    question: Annotated[str, Field(min_length=1, max_length=2048)]
    evidence: SourceArtifactRef | None = None
    answerability: Answerability
    expected_facts: tuple[Annotated[str, Field(min_length=1, max_length=1024)], ...] = Field(default_factory=tuple, max_length=64)
    forbidden_facts: tuple[Annotated[str, Field(min_length=1, max_length=1024)], ...] = Field(default_factory=tuple, max_length=64)
    relevant_evidence_ids: tuple[Annotated[str, Field(pattern=r"^evd_[a-f0-9]{32}$")], ...] = Field(default_factory=tuple, max_length=100)
    required_citation_keys: tuple[Annotated[str, Field(pattern=r"^cit_[a-f0-9]{32}$")], ...] = Field(default_factory=tuple, max_length=100)
    deterministic_answer: Annotated[str, Field(min_length=1, max_length=4096)] | None = None


class DatasetContent(DatasetContract):
    schema_revision: Literal["GoldenDataset/v1"] = "GoldenDataset/v1"
    taxonomy: SliceTaxonomy = DEFAULT_TAXONOMY
    annotations: tuple[DocumentAnnotation, ...] = Field(default_factory=tuple, max_length=1000)
    query_cases: tuple[QueryCase, ...] = Field(default_factory=tuple, max_length=1000)

    @model_validator(mode="after")
    def unique_cases(self) -> "DatasetContent":
        identifiers = [item.id for item in (*self.annotations, *self.query_cases)]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("dataset case identifiers must be unique")
        return self


class GoldenDataset(DatasetContract):
    id: UUID
    revision_id: UUID
    revision: int = Field(ge=1)
    parent_revision_id: UUID | None = None
    content: DatasetContent
    content_digest: Digest
    operation: Literal["create", "edit", "import"]
    created_at: datetime


def canonical_bytes(value: DatasetContract) -> bytes:
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def content_digest(content: DatasetContent) -> str:
    return hashlib.sha256(canonical_bytes(content)).hexdigest()
