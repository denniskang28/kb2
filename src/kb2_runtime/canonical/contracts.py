from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kb2_runtime.trace.contracts import QualitySignal

MAX_TEXT = 16_384
MAX_ELEMENTS = 4_096
MAX_TABLES = 256
MAX_CELLS = 16_384
MAX_LIST_ITEMS = 1_024
MAX_RELATIONSHIPS = 1_024
StableId = Annotated[str, Field(pattern=r"^[a-z]+_[a-f0-9]{16,64}$")]
BoundedText = Annotated[str, Field(max_length=MAX_TEXT)]


class CanonicalContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DocumentMetadata(CanonicalContract):
    title: BoundedText | None = None
    language: Annotated[str, Field(pattern=r"^[A-Za-z0-9-]{1,32}$")] | None = None
    media_type: Annotated[str, Field(pattern=r"^[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]{1,127}$")] | None = None


class Provenance(CanonicalContract):
    source_artifact_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")
    source_content_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    adapter_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.@-]{0,63}$")]


class ElementProvenance(CanonicalContract):
    adapter_element_ref: Annotated[str, Field(min_length=1, max_length=256)]
    source_confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class PdfLocator(CanonicalContract):
    kind: Literal["pdf"] = "pdf"
    page_number: int = Field(gt=0)
    x0: float = Field(ge=0, le=1, allow_inf_nan=False)
    y0: float = Field(ge=0, le=1, allow_inf_nan=False)
    x1: float = Field(ge=0, le=1, allow_inf_nan=False)
    y1: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def normalized_region(self) -> "PdfLocator":
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("PDF locator region must be normalized")
        return self


class PresentationLocator(CanonicalContract):
    kind: Literal["presentation"] = "presentation"
    slide_number: int = Field(gt=0)
    object_id: Annotated[str, Field(min_length=1, max_length=128)]


class SpreadsheetLocator(CanonicalContract):
    kind: Literal["spreadsheet"] = "spreadsheet"
    sheet_name: Annotated[str, Field(min_length=1, max_length=128)]
    range: Annotated[str, Field(pattern=r"^[A-Z]+[1-9][0-9]*(?::[A-Z]+[1-9][0-9]*)?$")]


class HtmlLocator(CanonicalContract):
    kind: Literal["html"] = "html"
    path: Annotated[str, Field(min_length=1, max_length=512)]
    anchor: Annotated[str, Field(min_length=1, max_length=256)]


class WordProcessingLocator(CanonicalContract):
    kind: Literal["word_processing"] = "word_processing"
    heading_anchor: Annotated[str, Field(min_length=1, max_length=256)]
    paragraph_index: int = Field(gt=0)


Locator = Annotated[PdfLocator | PresentationLocator | SpreadsheetLocator | HtmlLocator | WordProcessingLocator, Field(discriminator="kind")]


class ListItem(CanonicalContract):
    text: BoundedText
    level: int = Field(ge=0, le=32)


class CanonicalElement(CanonicalContract):
    id: StableId
    kind: Literal["heading", "paragraph", "list", "figure", "caption", "code", "table"]
    reading_order: int = Field(ge=0)
    parent_id: StableId | None = None
    locator: Locator
    provenance: ElementProvenance | None = None
    quality_signals: tuple[QualitySignal, ...] = Field(default_factory=tuple, max_length=64)
    level: int | None = Field(default=None, ge=1, le=9)
    text: BoundedText | None = None
    ordered: bool | None = None
    items: tuple[ListItem, ...] | None = Field(default=None, max_length=MAX_LIST_ITEMS)
    alt_text: BoundedText | None = None
    language: Annotated[str, Field(pattern=r"^[A-Za-z0-9+.-]{1,64}$")] | None = None
    table_id: StableId | None = None

    @model_validator(mode="after")
    def kind_shape(self) -> "CanonicalElement":
        if self.kind == "heading" and (self.text is None or self.level is None):
            raise ValueError("heading requires text and level")
        if self.kind in {"paragraph", "caption", "code"} and self.text is None:
            raise ValueError(f"{self.kind} requires text")
        if self.kind == "list" and (self.ordered is None or self.items is None):
            raise ValueError("list requires ordered and items")
        if self.kind == "table" and self.table_id is None:
            raise ValueError("table requires table_id")
        if self.kind != "table" and self.table_id is not None:
            raise ValueError("only table elements may reference table_id")
        return self


class TableCell(CanonicalContract):
    id: StableId
    text: BoundedText
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(gt=0)
    column_span: int = Field(gt=0)
    is_header: bool = False


class CanonicalTable(CanonicalContract):
    id: StableId
    element_id: StableId
    rows: int = Field(gt=0, le=512)
    columns: int = Field(gt=0, le=512)
    locator: Locator
    cells: tuple[TableCell, ...] = Field(min_length=1, max_length=MAX_CELLS)
    header_cell_ids: tuple[StableId, ...] = Field(default_factory=tuple, max_length=MAX_CELLS)
    caption_element_id: StableId | None = None
    related_element_ids: tuple[StableId, ...] = Field(default_factory=tuple, max_length=MAX_RELATIONSHIPS)

    @model_validator(mode="after")
    def valid_grid(self) -> "CanonicalTable":
        if len({cell.id for cell in self.cells}) != len(self.cells):
            raise ValueError("table cell IDs must be unique")
        grid: set[tuple[int, int]] = set()
        cell_ids = {cell.id: cell for cell in self.cells}
        for cell in self.cells:
            if cell.row + cell.row_span > self.rows or cell.column + cell.column_span > self.columns:
                raise ValueError("table cell span is out of bounds")
            for row in range(cell.row, cell.row + cell.row_span):
                for column in range(cell.column, cell.column + cell.column_span):
                    if (row, column) in grid:
                        raise ValueError("table cells must not overlap")
                    grid.add((row, column))
        if len(grid) != self.rows * self.columns:
            raise ValueError("table cells must cover the grid")
        if len(set(self.header_cell_ids)) != len(self.header_cell_ids) or any(
            identifier not in cell_ids or not cell_ids[identifier].is_header for identifier in self.header_cell_ids
        ):
            raise ValueError("table headers must identify header cells")
        if len(set(self.related_element_ids)) != len(self.related_element_ids):
            raise ValueError("table relationships must be unique")
        return self


class CanonicalDocument(CanonicalContract):
    schema_version: Literal["CanonicalDocument/v1"] = "CanonicalDocument/v1"
    document_id: StableId
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    provenance: Provenance
    elements: tuple[CanonicalElement, ...] = Field(min_length=1, max_length=MAX_ELEMENTS)
    tables: tuple[CanonicalTable, ...] = Field(default_factory=tuple, max_length=MAX_TABLES)
    quality_signals: tuple[QualitySignal, ...] = Field(default_factory=tuple, max_length=64)

    @model_validator(mode="after")
    def coherent_structure(self) -> "CanonicalDocument":
        ids = {element.id for element in self.elements}
        if len(ids) != len(self.elements):
            raise ValueError("element IDs must be unique")
        if [element.reading_order for element in self.elements] != list(range(len(self.elements))):
            raise ValueError("reading order must be contiguous and ordered")
        seen: set[str] = set()
        for element in self.elements:
            if element.parent_id and (element.parent_id not in seen or element.parent_id == element.id):
                raise ValueError("element parent must be an earlier element")
            seen.add(element.id)
        tables = {table.id: table for table in self.tables}
        if len(tables) != len(self.tables):
            raise ValueError("table IDs must be unique")
        if {element.table_id for element in self.elements if element.kind == "table"} != set(tables):
            raise ValueError("table elements and tables must match")
        for table in self.tables:
            if table.element_id not in ids or next(item for item in self.elements if item.id == table.element_id).kind != "table":
                raise ValueError("table must reference a table element")
            for related in (*table.related_element_ids, *((table.caption_element_id,) if table.caption_element_id else ())):
                if related not in ids:
                    raise ValueError("table references an unknown element")
        return self


class FixtureElement(CanonicalContract):
    kind: Literal["heading", "paragraph", "list", "figure", "caption", "code", "table"]
    reading_order: int = Field(ge=0)
    parent_reading_order: int | None = Field(default=None, ge=0)
    locator: Locator
    level: int | None = Field(default=None, ge=1, le=9)
    text: BoundedText | None = None
    ordered: bool | None = None
    items: tuple[ListItem, ...] | None = Field(default=None, max_length=MAX_LIST_ITEMS)
    alt_text: BoundedText | None = None
    language: Annotated[str, Field(pattern=r"^[A-Za-z0-9+.-]{1,64}$")] | None = None
    quality_signals: tuple[QualitySignal, ...] = Field(default_factory=tuple, max_length=64)

    @model_validator(mode="after")
    def fixture_shape(self) -> "FixtureElement":
        CanonicalElement(id="elm_0000000000000000", table_id="tbl_0000000000000000" if self.kind == "table" else None, **self.model_dump(exclude={"parent_reading_order"}))
        return self


class FixtureTableCell(CanonicalContract):
    text: BoundedText
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(gt=0)
    column_span: int = Field(gt=0)
    is_header: bool = False


class FixtureTable(CanonicalContract):
    element_reading_order: int = Field(ge=0)
    rows: int = Field(gt=0, le=512)
    columns: int = Field(gt=0, le=512)
    locator: Locator
    cells: tuple[FixtureTableCell, ...] = Field(min_length=1, max_length=MAX_CELLS)
    header_cell_positions: tuple[tuple[int, int], ...] = Field(default_factory=tuple, max_length=MAX_CELLS)
    caption_reading_order: int | None = Field(default=None, ge=0)
    related_reading_orders: tuple[int, ...] = Field(default_factory=tuple, max_length=MAX_RELATIONSHIPS)


class ProviderFixture(CanonicalContract):
    adapter_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.@-]{0,63}$")]
    source_content_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    elements: tuple[FixtureElement, ...] = Field(min_length=1, max_length=MAX_ELEMENTS)
    tables: tuple[FixtureTable, ...] = Field(default_factory=tuple, max_length=MAX_TABLES)
    quality_signals: tuple[QualitySignal, ...] = Field(default_factory=tuple, max_length=64)

    @model_validator(mode="after")
    def ordered_fixture(self) -> "ProviderFixture":
        if [element.reading_order for element in self.elements] != list(range(len(self.elements))):
            raise ValueError("fixture reading order must be contiguous and ordered")
        return self
