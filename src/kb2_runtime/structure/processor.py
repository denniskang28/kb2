from __future__ import annotations

import json

from pydantic import ValidationError

from kb2_runtime.canonical.contracts import CanonicalDocument, CanonicalElement
from kb2_runtime.canonical.serializer import canonical_document_bytes, locator_key
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

from .contracts import StructureStrategy

MAX_CANONICAL_BYTES = 16 * 1024 * 1024


def process(content: bytes, strategy: StructureStrategy) -> CanonicalDocument:
    if len(content) > MAX_CANONICAL_BYTES:
        raise PluginError(PluginErrorCode.CANONICAL_FIELD_UNBOUNDED)
    try:
        raw = json.loads(content.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("canonical document must be an object")
        document = CanonicalDocument.model_validate(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise PluginError(_error_code(exc)) from exc

    try:
        if strategy is StructureStrategy.HIERARCHY:
            document = _hierarchy(document)
        elif strategy is StructureStrategy.LAYOUT:
            document = _layout(document)
        _validate_tables(document)
        return document
    except (ValidationError, ValueError) as exc:
        raise PluginError(PluginErrorCode.CANONICAL_DOCUMENT_INVALID) from exc


def _hierarchy(document: CanonicalDocument) -> CanonicalDocument:
    stack: list[CanonicalElement] = []
    elements: list[CanonicalElement] = []
    for element in document.elements:
        parent_id = element.parent_id
        if element.kind == "heading":
            while stack and stack[-1].level >= element.level:  # type: ignore[operator]
                stack.pop()
            if stack and element.level > stack[-1].level + 1:  # type: ignore[operator]
                raise ValueError("heading levels must not skip")
            if parent_id is None and stack:
                parent_id = stack[-1].id
            result = element.model_copy(update={"parent_id": parent_id})
            stack.append(result)
        else:
            if parent_id is None and stack:
                parent_id = stack[-1].id
            result = element.model_copy(update={"parent_id": parent_id})
        elements.append(result)
    return document.model_copy(update={"elements": tuple(elements)})


def _layout(document: CanonicalDocument) -> CanonicalDocument:
    if any(element.locator.kind != "pdf" for element in document.elements):
        raise ValueError("layout strategy requires PDF locators")
    ordered = sorted(document.elements, key=lambda item: (
        item.locator.page_number, item.locator.y0, item.locator.x0, item.reading_order  # type: ignore[union-attr]
    ))
    positions = {element.id: index for index, element in enumerate(ordered)}
    if any(element.parent_id and positions[element.parent_id] >= positions[element.id] for element in ordered):
        raise ValueError("layout order would place parent after child")
    elements = tuple(element.model_copy(update={"reading_order": index}) for index, element in enumerate(ordered))
    return document.model_copy(update={"elements": elements})


def _validate_tables(document: CanonicalDocument) -> None:
    elements = {element.id: element for element in document.elements}
    for table in document.tables:
        element = elements[table.element_id]
        if locator_key(element.locator) != locator_key(table.locator):
            raise ValueError("table locator must match table element locator")
        if table.caption_element_id and elements[table.caption_element_id].kind != "caption":
            raise ValueError("table caption must reference caption element")
        if table.element_id in table.related_element_ids:
            raise ValueError("table must not relate to itself")


def canonical_bytes(document: CanonicalDocument) -> bytes:
    return canonical_document_bytes(document)


def _error_code(error: Exception) -> PluginErrorCode:
    text = str(error).lower()
    if "max_length" in text or "too_long" in text or "too long" in text:
        return PluginErrorCode.CANONICAL_FIELD_UNBOUNDED
    return PluginErrorCode.CANONICAL_INPUT_INVALID
