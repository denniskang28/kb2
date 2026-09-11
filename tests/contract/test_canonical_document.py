from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from kb2_runtime.canonical.contracts import CanonicalDocument, ProviderFixture
from kb2_runtime.canonical.normalizer import normalize_fixture
from kb2_runtime.canonical.serializer import canonical_document_bytes


SOURCE = hashlib.sha256(b"representative source").hexdigest()


def fixture() -> dict[str, object]:
    return {
        "adapter_id": "fixture.parser@1", "source_content_digest": SOURCE,
        "metadata": {"title": "Example", "language": "en", "media_type": "application/pdf"},
        "quality_signals": [{"name": "source_quality", "status": "PASS", "summary": "checked"}],
        "elements": [
            {"kind": "heading", "reading_order": 0, "locator": {"kind": "pdf", "page_number": 1, "x0": 0, "y0": 0, "x1": 1, "y1": 1}, "level": 1, "text": "Title"},
            {"kind": "paragraph", "reading_order": 1, "parent_reading_order": 0, "locator": {"kind": "presentation", "slide_number": 1, "object_id": "title"}, "text": "Body"},
            {"kind": "list", "reading_order": 2, "parent_reading_order": 0, "locator": {"kind": "spreadsheet", "sheet_name": "Sheet1", "range": "A1:A2"}, "ordered": True, "items": [{"text": "one", "level": 0}]},
            {"kind": "figure", "reading_order": 3, "locator": {"kind": "html", "path": "main/figure[1]", "anchor": "chart"}, "alt_text": "Chart"},
            {"kind": "caption", "reading_order": 4, "locator": {"kind": "word_processing", "heading_anchor": "figures", "paragraph_index": 1}, "text": "Figure 1"},
            {"kind": "code", "reading_order": 5, "locator": {"kind": "pdf", "page_number": 2, "x0": 0, "y0": 0, "x1": 1, "y1": 1}, "text": "print(1)", "language": "python"},
            {"kind": "table", "reading_order": 6, "locator": {"kind": "spreadsheet", "sheet_name": "Sheet1", "range": "A4:B5"}},
        ],
        "tables": [{
            "element_reading_order": 6, "rows": 2, "columns": 2,
            "locator": {"kind": "spreadsheet", "sheet_name": "Sheet1", "range": "A4:B5"},
            "cells": [
                {"text": "Name", "row": 0, "column": 0, "row_span": 1, "column_span": 1, "is_header": True},
                {"text": "Value", "row": 0, "column": 1, "row_span": 1, "column_span": 1, "is_header": True},
                {"text": "A", "row": 1, "column": 0, "row_span": 1, "column_span": 1},
                {"text": "1", "row": 1, "column": 1, "row_span": 1, "column_span": 1},
            ], "header_cell_positions": [[0, 0], [0, 1]], "caption_reading_order": 4, "related_reading_orders": [1],
        }],
    }


def test_fixture_normalizes_all_required_shapes_with_stable_json() -> None:
    value = ProviderFixture.model_validate(fixture())
    document = normalize_fixture(value, "c7f1c2c2-2bd1-4ff3-a641-0f52f50bfdd1")
    encoded = canonical_document_bytes(document)
    assert CanonicalDocument.model_validate_json(encoded) == document
    assert canonical_document_bytes(CanonicalDocument.model_validate_json(encoded)) == encoded
    assert [item.reading_order for item in document.elements] == list(range(7))
    assert document.tables[0].caption_element_id == document.elements[4].id
    assert {item.locator.kind for item in document.elements} == {"pdf", "presentation", "spreadsheet", "html", "word_processing"}
    assert normalize_fixture(value, "c7f1c2c2-2bd1-4ff3-a641-0f52f50bfdd1").document_id == document.document_id


@pytest.mark.parametrize("mutate", [
    lambda item: item["elements"].__setitem__(1, {**item["elements"][1], "reading_order": 0}),
    lambda item: item["elements"].__setitem__(1, {**item["elements"][1], "parent_reading_order": 6}),
    lambda item: item["tables"][0]["cells"].__setitem__(3, {**item["tables"][0]["cells"][3], "row": 0}),
    lambda item: item["tables"][0].__setitem__("header_cell_positions", [[1, 0]]),
    lambda item: item["elements"].__setitem__(0, {**item["elements"][0], "locator": {"kind": "pdf", "page_number": 1, "x0": 1, "y0": 0, "x1": 0, "y1": 1}}),
])
def test_invalid_structure_is_rejected(mutate: object) -> None:
    item = fixture()
    mutate(item)  # type: ignore[operator]
    with pytest.raises((ValidationError, ValueError)):
        value = ProviderFixture.model_validate(item)
        normalize_fixture(value, "c7f1c2c2-2bd1-4ff3-a641-0f52f50bfdd1")


def test_provider_fixture_rejects_unknown_or_unbounded_fields() -> None:
    with pytest.raises(ValidationError):
        ProviderFixture.model_validate({**fixture(), "provider_sdk": object()})
    oversized = fixture()
    oversized["elements"][1]["text"] = "x" * 16_385
    with pytest.raises(ValidationError):
        ProviderFixture.model_validate(oversized)


def test_non_table_element_cannot_carry_a_table_reference() -> None:
    document = normalize_fixture(ProviderFixture.model_validate(fixture()), "c7f1c2c2-2bd1-4ff3-a641-0f52f50bfdd1")
    invalid = document.model_dump(mode="json")
    invalid["elements"][1]["table_id"] = document.tables[0].id
    with pytest.raises(ValidationError, match="only table elements"):
        CanonicalDocument.model_validate(invalid)


@pytest.mark.parametrize("mutate", [
    lambda value: value["elements"][1].update(id=value["elements"][0]["id"]),
    lambda value: value["elements"][0].update(parent_id=value["elements"][1]["id"]),
    lambda value: value["elements"][0].pop("locator"),
    lambda value: value["tables"][0]["cells"][0].update(row_span=3),
    lambda value: value["tables"][0].update(related_element_ids=["elm_0000000000000000"]),
])
def test_canonical_payload_rejects_invalid_identity_structure_locators_and_tables(mutate: object) -> None:
    provider = ProviderFixture.model_validate(fixture())
    document = normalize_fixture(provider, "c7f1c2c2-2bd1-4ff3-a641-0f52f50bfdd1")
    payload = document.model_dump(mode="json")
    mutate(payload)  # type: ignore[operator]
    with pytest.raises(ValidationError):
        CanonicalDocument.model_validate(payload)
