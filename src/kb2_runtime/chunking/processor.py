from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import ValidationError

from kb2_runtime.canonical.contracts import CanonicalDocument, CanonicalElement, CanonicalTable
from kb2_runtime.canonical.serializer import locator_key
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

from .contracts import Chunk, ChunkCitation, ChunkSet, ChunkStrategy, ChunkerConfig, EnrichmentField, EnrichmentProvenance
from .serializer import chunk_set_bytes

MAX_CANONICAL_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class Segment:
    element: CanonicalElement
    content: str
    context: tuple[str, ...]
    citation_elements: tuple[CanonicalElement, ...] = ()

    @property
    def tokens(self) -> int:
        return token_count(self.content)


def token_count(content: str) -> int:
    return len(content.split())


def process(content: bytes, config: ChunkerConfig) -> ChunkSet:
    if len(content) > MAX_CANONICAL_BYTES:
        raise PluginError(PluginErrorCode.CANONICAL_FIELD_UNBOUNDED)
    try:
        document = CanonicalDocument.model_validate_json(content)
        segments = render_segments(document, config)
        if config.strategy == ChunkStrategy.PARENT_CHILD:
            chunks = _parent_child(document, segments, config)
        elif config.strategy == ChunkStrategy.HIERARCHY:
            chunks = _hierarchy(document, segments, config)
        elif config.strategy == ChunkStrategy.TABLE:
            chunks = _table(document, segments, config)
        else:
            chunks = _fixed(document, segments, config)
        return ChunkSet(document_id=document.document_id, metadata=document.metadata, language=document.metadata.language, chunker_configuration=config, chunks=tuple(chunks))
    except PluginError:
        raise
    except (ValidationError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        raise PluginError(PluginErrorCode.CANONICAL_INPUT_INVALID) from exc


def render_segments(document: CanonicalDocument, config: ChunkerConfig) -> list[Segment]:
    tables = {item.element_id: item for item in document.tables}
    headings: list[tuple[int, str]] = []
    result = []
    for element in document.elements:
        if element.kind == "heading":
            while headings and headings[-1][0] >= element.level:  # type: ignore[operator]
                headings.pop()
            headings.append((element.level or 1, element.text or ""))
        contents = _render_table_segments(tables[element.id], document, config.max_tokens) if element.kind == "table" else (_render_element(element),)
        for content in contents:
            if not content:
                continue
            citations = (element,)
            if element.kind == "table":
                table = tables[element.id]
                citation_ids = (element.id, *table.related_element_ids, *((table.caption_element_id,) if table.caption_element_id else ()))
                citations = tuple(item for item in document.elements if item.id in citation_ids)
            result.append(Segment(element, content, tuple(item[1] for item in headings), citations))
    if not result:
        raise ValueError("document has no renderable elements")
    return result


def _render_element(element: CanonicalElement) -> str:
    if element.kind == "list":
        return "\n".join(f"{'  ' * item.level}- {item.text}" for item in element.items or ())
    if element.kind in {"heading", "paragraph", "caption", "code"}:
        return element.text or ""
    return ""


def _render_table_segments(table: CanonicalTable, document: CanonicalDocument, max_tokens: int) -> tuple[str, ...]:
    elements = {item.id: item for item in document.elements}
    caption = elements[table.caption_element_id].text if table.caption_element_id else None
    headers = [cell for cell in sorted(table.cells, key=lambda item: (item.row, item.column)) if cell.is_header]
    rows: list[str] = []
    for row in range(table.rows):
        cells = [cell for cell in sorted(table.cells, key=lambda item: item.column) if cell.row == row]
        rows.append(" | ".join(f"c{cell.column}[{cell.row_span}x{cell.column_span}]={cell.text}" for cell in cells))
    prefix = ([f"Table: {caption}"] if caption else []) + (["Headers: " + " | ".join(cell.text for cell in headers)] if headers else [])
    header = "\n".join(prefix)
    if token_count(header) > max_tokens or any(token_count(row) > max_tokens for row in rows):
        raise PluginError(PluginErrorCode.CANONICAL_FIELD_UNBOUNDED)
    groups: list[str] = []
    current = header
    for row in rows:
        candidate = "\n".join(item for item in (current, row) if item)
        if current and token_count(candidate) > max_tokens:
            groups.append(current)
            current = "\n".join(item for item in (header, row) if item)
        else:
            current = candidate
    if current:
        groups.append(current)
    return tuple(groups)


def _fixed(document: CanonicalDocument, segments: list[Segment], config: ChunkerConfig) -> list[Chunk]:
    groups = _window_groups(segments, config)
    return [_make_chunk(document, group, config, None) for group in groups]


def _window_groups(segments: list[Segment], config: ChunkerConfig) -> list[list[Segment]]:
    for segment in segments:
        if segment.tokens > config.max_tokens:
            raise PluginError(PluginErrorCode.CANONICAL_FIELD_UNBOUNDED)
    groups, current = [], []
    current_tokens = 0
    for segment in segments:
        if current and current_tokens + segment.tokens > config.max_tokens:
            groups.append(current)
            overlap: list[Segment] = []
            used = 0
            # Preserve only whole trailing segments that fit both the requested
            # overlap and the remaining capacity for the incoming segment.
            overlap_limit = min(config.overlap_tokens, config.max_tokens - segment.tokens)
            for prior in reversed(current):
                if used + prior.tokens > overlap_limit:
                    break
                overlap.insert(0, prior)
                used += prior.tokens
            current, current_tokens = overlap, used
        current.append(segment)
        current_tokens += segment.tokens
    if current:
        groups.append(current)
    return groups


def _hierarchy(document: CanonicalDocument, segments: list[Segment], config: ChunkerConfig) -> list[Chunk]:
    groups: list[list[Segment]] = []
    current: list[Segment] = []
    context: tuple[str, ...] | None = None
    for segment in segments:
        if current and segment.context != context:
            groups.extend(_window_groups(current, config))
            current = []
        current.append(segment)
        context = segment.context
    if current:
        groups.extend(_window_groups(current, config))
    return [_make_chunk(document, group, config, None) for group in groups]


def _table(document: CanonicalDocument, segments: list[Segment], config: ChunkerConfig) -> list[Chunk]:
    groups: list[list[Segment]] = []
    prose: list[Segment] = []
    for segment in segments:
        if segment.element.kind == "table":
            if prose:
                groups.extend(_window_groups(prose, config)); prose = []
            # A table segment is deliberately indivisible: it preserves its exact cell semantics.
            if segment.tokens > config.max_tokens:
                raise PluginError(PluginErrorCode.CANONICAL_FIELD_UNBOUNDED)
            groups.append([segment])
        else:
            prose.append(segment)
    if prose:
        groups.extend(_window_groups(prose, config))
    return [_make_chunk(document, group, config, None) for group in groups]


def _parent_child(document: CanonicalDocument, segments: list[Segment], config: ChunkerConfig) -> list[Chunk]:
    child_groups = _window_groups(segments, config)
    parent_groups: list[list[list[Segment]]] = []
    current: list[list[Segment]] = []
    for child in child_groups:
        candidate = [*current, child]
        flattened = [segment for group in candidate for segment in group]
        if current and (len(candidate) > config.max_children or token_count("\n".join(item.content for item in flattened)) > config.max_tokens):
            parent_groups.append(current)
            current = [child]
        else:
            current = candidate
    if current:
        parent_groups.append(current)
    parents = [_make_chunk(document, [segment for child in group for segment in child], config, None) for group in parent_groups]
    children: list[Chunk] = []
    for index, (parent, assigned) in enumerate(zip(parents, parent_groups, strict=True)):
        child_ids = []
        for child_group in assigned:
            child = _make_chunk(document, child_group, config, parent.chunk_id)
            children.append(child); child_ids.append(child.chunk_id)
        parents[index] = parent.model_copy(update={"child_chunk_ids": tuple(child_ids)})
    return [*parents, *children]


def _chunk_data(segments: list[Segment]) -> tuple[str, tuple[str, ...]]:
    return "\n".join(item.content for item in segments), tuple(element.id for item in segments for element in item.citation_elements)


def _make_chunk(document: CanonicalDocument, segments: list[Segment], config: ChunkerConfig, parent_id: str | None) -> Chunk:
    content, identifiers = _chunk_data(segments)
    count = token_count(content)
    if not content or count > config.max_tokens:
        raise PluginError(PluginErrorCode.CANONICAL_FIELD_UNBOUNDED)
    # Overlap can repeat segments; a Chunk cites each source element once in reading order.
    unique = tuple(dict.fromkeys(identifiers))
    citations = tuple(dict.fromkeys((element.id, locator_key(element.locator)) for item in segments for element in item.citation_elements))
    citations = tuple(ChunkCitation(element_id=identifier, locator=next(element.locator for item in segments for element in item.citation_elements if element.id == identifier)) for identifier, _ in citations)
    chunk_id = _chunk_id(document.document_id, config, unique, parent_id, content)
    return Chunk(chunk_id=chunk_id, content=content, token_count=count, source_element_ids=unique, citations=citations, parent_chunk_id=parent_id, hierarchy_context=segments[0].context, language=next((item.element.language for item in segments if item.element.language), document.metadata.language))


def enrich(content: bytes, fields: dict[str, object], plugin_id: str, configuration_digest: str) -> ChunkSet:
    try:
        chunk_set = ChunkSet.model_validate_json(content)
        for chunk in chunk_set.chunks:
            expected = _chunk_id(chunk_set.document_id, chunk_set.chunker_configuration, chunk.source_element_ids, chunk.parent_chunk_id, chunk.content)
            if chunk.chunk_id != expected:
                raise ValueError("chunk identity does not match its canonical fields")
        updated = []
        for chunk in chunk_set.chunks:
            if set(fields) & set(chunk.enrichments):
                raise ValueError("enrichment field already exists")
            values = {name: EnrichmentField(value=value, provenance=EnrichmentProvenance(producer_plugin_id=plugin_id, configuration_digest=configuration_digest, source_chunk_id=chunk.chunk_id)) for name, value in fields.items()}
            updated.append(chunk.model_copy(update={"enrichments": {**chunk.enrichments, **values}}))
        return chunk_set.model_copy(update={"chunks": tuple(updated)})
    except (ValidationError, ValueError, TypeError) as exc:
        raise PluginError(PluginErrorCode.CANONICAL_INPUT_INVALID) from exc


def canonical_bytes(chunk_set: ChunkSet) -> bytes:
    return chunk_set_bytes(chunk_set)


def _chunk_id(document_id: str, config: ChunkerConfig, element_ids: tuple[str, ...], parent_id: str | None, content: str) -> str:
    identity = json.dumps({"schema": "ChunkSet/v1", "document_id": document_id, "strategy": config.strategy, "configuration": config.model_dump(mode="json"), "elements": element_ids, "parent": parent_id, "content": content}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "chk_" + hashlib.sha256(identity.encode()).hexdigest()[:32]
