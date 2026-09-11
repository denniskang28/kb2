from __future__ import annotations

import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

from .contracts import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalTable,
    FixtureTable,
    ProviderFixture,
    Provenance,
    TableCell,
)
from .serializer import canonical_document_bytes, locator_key, stable_id

MAX_PROVIDER_FIXTURE_BYTES = 512 * 1024


class CanonicalNormalizerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CanonicalNormalizer:
    """Converts the deliberately typed diagnostic fixture into CanonicalDocument/v1."""

    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        source = await context.input(context.invocation.inputs[0].id)
        if len(source.content) > MAX_PROVIDER_FIXTURE_BYTES:
            raise PluginError(PluginErrorCode.CANONICAL_FIELD_UNBOUNDED)
        try:
            raw = json.loads(source.content.decode("utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("fixture must be an object")
            fixture = ProviderFixture.model_validate(raw)
            document = normalize_fixture(fixture, source.reference.id, source.reference.content_digest)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, TypeError, KeyError) as exc:
            raise PluginError(_error_code(exc)) from exc
        return PluginInvocationResult(
            outputs=(PluginOutput(
                artifact_type="canonical.document",
                schema_revision="v1",
                content=canonical_document_bytes(document),
                summary="canonical document normalized",
                metrics=({"name": "canonical_elements", "value": len(document.elements)},),
                quality_signals=({"name": "canonical_normalization", "status": "PASS", "summary": "validated"},),
            ),),
            summary="canonical document normalized",
        )


def _error_code(error: Exception) -> PluginErrorCode:
    text = str(error).lower()
    if "max_length" in text or "too_long" in text or "too long" in text:
        return PluginErrorCode.CANONICAL_FIELD_UNBOUNDED
    return PluginErrorCode.CANONICAL_INPUT_INVALID


def normalize_fixture(fixture: ProviderFixture, source_artifact_id: UUID, input_artifact_digest: str | None = None) -> CanonicalDocument:
    # Identity follows the immutable parent Artifact rather than adapter-local values.
    source = input_artifact_digest or fixture.source_content_digest
    element_ids = {
        item.reading_order: stable_id("elm", source, "CanonicalDocument/v1", item.kind, str(item.reading_order), locator_key(item.locator))
        for item in fixture.elements
    }
    elements = []
    for item in fixture.elements:
        table_id = stable_id("tbl", source, str(item.reading_order)) if item.kind == "table" else None
        elements.append(CanonicalElement(
            id=element_ids[item.reading_order], kind=item.kind, reading_order=item.reading_order,
            parent_id=element_ids[item.parent_reading_order] if item.parent_reading_order is not None else None,
            locator=item.locator, level=item.level, text=item.text, ordered=item.ordered, items=item.items,
            alt_text=item.alt_text, language=item.language, table_id=table_id, quality_signals=item.quality_signals,
        ))
    tables = tuple(_table_from_fixture(table, source, element_ids) for table in fixture.tables)
    return CanonicalDocument(
        document_id=stable_id("doc", source, "CanonicalDocument/v1"), metadata=fixture.metadata,
        provenance=Provenance(source_artifact_id=str(source_artifact_id), source_content_digest=fixture.source_content_digest, adapter_id=fixture.adapter_id),
        elements=tuple(elements), tables=tables, quality_signals=fixture.quality_signals,
    )


def _table_from_fixture(table: FixtureTable, source: str, element_ids: dict[int, str]) -> CanonicalTable:
    table_id = stable_id("tbl", source, str(table.element_reading_order))
    cells = tuple(TableCell(
        id=stable_id("cel", source, str(table.element_reading_order), str(cell.row), str(cell.column)),
        text=cell.text, row=cell.row, column=cell.column, row_span=cell.row_span, column_span=cell.column_span,
        is_header=cell.is_header,
    ) for cell in table.cells)
    by_position = {(cell.row, cell.column): cell.id for cell in cells}
    return CanonicalTable(
        id=table_id, element_id=element_ids[table.element_reading_order], rows=table.rows, columns=table.columns,
        locator=table.locator, cells=cells,
        header_cell_ids=tuple(by_position[position] for position in table.header_cell_positions),
        caption_element_id=element_ids[table.caption_reading_order] if table.caption_reading_order is not None else None,
        related_element_ids=tuple(element_ids[index] for index in table.related_reading_orders),
    )
