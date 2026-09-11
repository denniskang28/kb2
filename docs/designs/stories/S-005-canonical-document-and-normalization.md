# Story Design: S-005 - Canonical Document And Normalization Boundary

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-005-canonical-document-and-normalization.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-11; pipeline delivery
  started 2026-09-11.
- **Material Decisions Requiring Approval:** None. The pipeline invocation
  authorizes the physical schema and normalizer implementation choices below;
  they preserve the confirmed `CanonicalDocument/v1` boundary.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add frozen, extra-forbidden Pydantic contracts for `CanonicalDocument/v1`, typed elements, hierarchy, metadata, provenance, locators, tables, and quality signals. Serialize the validated model using sorted-key, compact ASCII JSON. | Contract fixture contains every required element kind, hierarchy, reading order, table relationships, metadata, provenance, and quality signals; a round trip has byte-identical serialization. |
| 2 | Use a discriminated locator union for PDF, presentation, spreadsheet, HTML, and word-processing coordinates. Every element and table owns exactly one format-specific locator. | Parameterized locator fixtures validate and round-trip every locator variant, including each format's coordinates or anchors. |
| 3 | Extend the closed Artifact schema catalog with typed provider-fixture input and `canonical.document/v1`; register `normalizer.canonical@1`, which accepts only the typed provider Artifact, validates it, assigns deterministic element IDs, and commits the Canonical Artifact through the existing S-003 executor and S-002 lineage path. | Golden normalization fixtures execute through `PluginExecutor` and assert stable document/element IDs, order, canonical bytes, producing Plugin/configuration identity, and the exact parent Artifact reference. |
| 4 | Model cross-field invariants after parsing: unique IDs, valid parent graph and reading order, required locators, bounded strings/collections, table-cell grid/span validity, header/caption references, and relationship references. Map failures to bounded Canonical error codes. | Invalid matrix covers duplicate IDs, parent cycle/forward hierarchy, missing or mismatched locator, invalid/overlapping/out-of-bounds table spans, unknown relationships, and oversized provider fields; it asserts safe code/message and no successful output Artifact. |
| 5 | The normalizer's public Plugin boundary accepts `ArtifactReference` plus bytes and returns `PluginInvocationResult` with `canonical.document/v1` bytes only. Provider fixture classes stay inside the normalizer adapter; no SDK/object is included in Canonical contracts, Artifact manifests, traces, or output APIs. | Architecture regression uses a poison non-serializable provider object and asserts validation rejection; source/import and persisted-output assertions prove only Canonical JSON and normal Artifact references cross the runner boundary. |

## Current Code Findings

S-002 persists immutable bytes outside PostgreSQL and validates Artifact schema
pairs through the closed `trace.schemas.SUPPORTED_ARTIFACT_SCHEMAS` catalog.
It currently admits only `opaque.bytes/v1`. `ArtifactService` already derives
eligible downstream inputs from a valid manifest and captures parent Artifact
lineage, producer Plugin ID, configuration digest, metrics, quality signals,
and safe failures.

S-003 provides strict frozen Plugin contracts, an allowlisted in-memory
Registry, a common `PluginExecutor`, and both runner implementations. Registry
registration rejects schemas absent from the S-002 catalog, and executor
commits a Plugin result exclusively through `ArtifactService`. It currently
has only a synthetic byte-transform bootstrap Plugin. S-004 compiles typed
ports against the same Registry/catalog but does not execute plans. There is
no Canonical schema, parser/OCR implementation, provider SDK, ingestion
executor, database table, or UI to preserve or migrate.

## Proposed Approach

### Module Boundary And Artifact Schemas

Add a focused `kb2_runtime.canonical` package:

```text
kb2_runtime/canonical/
  contracts.py   # frozen CanonicalDocument/v1 and provider-fixture input models
  errors.py      # stable CanonicalErrorCode and CanonicalError
  serializer.py  # canonical JSON bytes and deterministic ID helpers
  normalizer.py  # allowlisted normalizer Plugin and its closed config model
```

Extend `kb2_runtime.trace.schemas` with exactly these S-005 pairs:

```text
("provider.parse-result-fixture", "v1")  # displayed as provider.parse-result-fixture/v1
("canonical.document", "v1")             # displayed as canonical.document/v1
```

`provider.parse-result-fixture/v1` is a bounded, test-support adapter payload,
not a universal provider payload schema and not a public SDK wrapper. It
exists solely to prove the normalizer boundary before S-006 introduces real
Parser/OCR adapters. `canonical.document/v1` is the durable payload schema
whose bytes are a `CanonicalDocument` serialized by the local serializer.
Existing `opaque.bytes/v1` support remains unchanged.

Register `normalizer.canonical@1` through repository-owned bootstrap with a
frozen, extra-forbidden empty configuration model, `kind="normalizer"`,
in-process runner, one named input port `provider_result`, and one named
output port `canonical_document`. The descriptor accepts only the fixture
schema and produces only `canonical.document/v1`. It has no path, command,
credential, provider client, environment, or arbitrary JSON configuration.
S-006 may register revisioned production Parser/OCR output schemas and
corresponding revisioned normalizer descriptors that reuse this package's
contract; it must not add a direct parser-to-Canonical shortcut.

### CanonicalDocument/v1 Payload Contract

The top-level frozen model contains only fields justified by the Story:

```text
schema_version: "CanonicalDocument/v1"
document_id: stable `doc_` SHA-256-derived identifier
metadata: { title?, language?, media_type? }
provenance: { source_artifact_id, source_content_digest, adapter_id }
elements: non-empty ordered element sequence
tables: table sequence
quality_signals: bounded trace QualitySignal sequence
```

All strings are UTF-8-safe after JSON decoding, bounded, and passed through
the existing safe metadata policy where they can become diagnostics. Unknown
fields, nested generic metadata maps, provider payload fragments, unbounded
text, non-finite values, and non-JSON data are rejected rather than preserved.
`document_id` is derived from the input Artifact digest and the fixed schema
version, not trusted from adapter input.

`elements` is a discriminated union with a stable common shape:

```text
id, kind, reading_order, parent_id?, locator, provenance?, quality_signals?
heading(level, text)
paragraph(text)
list(ordered, items[text, level])
figure(alt_text?)
caption(text)
code(text, language?)
table(table_id)
```

The initial schema intentionally avoids a general `attributes` bag. A list is
represented as one ordered element with bounded typed items; heading level and
code language are explicit only because the representative hierarchy/code
fixture needs them. `reading_order` is a unique contiguous zero-based sequence.
`parent_id` must reference an earlier element, cannot self-reference, and the
resulting directed hierarchy must be acyclic. This gives downstream chunking a
single unambiguous element identity and hierarchy representation without
duplicating child arrays.

Locators are a discriminated frozen union and retain only format-specific
coordinates/anchors needed by the Story:

| Kind | Required fields |
|---|---|
| `pdf` | positive `page_number`, normalized `(x0, y0, x1, y1)` region with `x1 >= x0`, `y1 >= y0` |
| `presentation` | positive `slide_number`, bounded `object_id` |
| `spreadsheet` | bounded `sheet_name`, bounded A1 `range` |
| `html` | bounded DOM `path`, bounded `anchor` |
| `word_processing` | bounded `heading_anchor`, positive `paragraph_index` |

Every element has a locator. A table separately carries its own locator so a
table may retain a precise source range even where its parent table element is
located at a broader page/object/range anchor.

Each `CanonicalTable` has `id`, `element_id`, dimensions, locator, bounded
cell sequence, `header_cell_ids`, optional `caption_element_id`, and bounded
`related_element_ids`. A `TableCell` has stable ID, text, zero-based row and
column starts, positive row/column spans, and `is_header`. Validation confirms
unique table/cell IDs; `element_id` refers to one `table` element; spans are in
bounds and neither overlap nor leave an uncovered grid location; explicit
header IDs identify only header cells; caption and related IDs reference known
elements; and duplicate relationships are rejected. The cell grid preserves
rows, columns, cells, spans, headers, captions, relationships, and source
location without speculative styling or provider-specific table fields.

Element-level `provenance` is optional only when it differs from the document
provenance and is limited to an adapter element reference plus bounded source
confidence. The top-level source Artifact identity is mandatory. Quality is
represented through existing `QualitySignal` contracts, at document and
element level, maintaining the S-002 safe/bounded representation.

### Deterministic Serialization And Normalization

`serializer.canonical_document_bytes(document)` uses
`model_dump(mode="json")` followed by `json.dumps(sort_keys=True,
separators=(",", ":"), ensure_ascii=True, allow_nan=False)`. Re-parsing those
bytes must reconstruct an equal frozen document and serialize to the identical
byte sequence. This serializer is the only canonical payload writer; raw
`model_dump_json` or provider JSON cannot be committed as a Canonical Artifact.

The fixture adapter input has a strict typed envelope with an adapter ID,
source artifact digest, bounded document metadata, and a bounded sequence of
fixture elements/tables using the same structural primitives but no stable
Canonical IDs. The normalizer obtains its single declared Artifact through
`PluginContext.input`, JSON-decodes bounded bytes, validates the fixture model,
derives the document ID, and materializes the Canonical models. It derives each
element ID from the source content digest, schema version, normalized kind,
reading order, and canonical locator bytes. Table and cell IDs derive from the
same source digest plus their table/cell positions. IDs never use UUIDs,
timestamps, provider object identity, host paths, or insertion order.

The normalizer passes the derived Canonical bytes as one `PluginOutput` to the
unmodified S-003 executor. S-003 then computes the output digest and S-002
atomically records its manifest, producer binding, configuration digest, and
the typed provider Artifact as the sole parent. The output has a bounded
summary and safe normalization metric/signal values only. Provider fixture
bytes are retained, if needed, only under their own diagnostic Artifact
locator; they never appear in Canonical JSON, summaries, or errors.

### Validation, Errors, And Security

Parsing limits are explicit: payload size is capped below the S-003 output
limit, IDs and textual fields have fixed practical maxima, and elements,
tables, cells, list items, relationships, quality signals, and nesting are all
bounded constants owned by `canonical.contracts`. The input decoder accepts
only UTF-8 JSON objects; no YAML, pickle, arbitrary mapping object, provider
SDK class, file reference, or executable/configuration field is accepted.

Add aligned `CanonicalErrorCode`/`PluginErrorCode`/`TraceErrorCode` values for
`CANONICAL_INPUT_INVALID`, `CANONICAL_DOCUMENT_INVALID`, and
`CANONICAL_FIELD_UNBOUNDED`. Each exposes a short allowlisted message and a
bounded JSON-pointer-like location in internal/test-facing Canonical errors;
the persisted S-002 `SafeError` uses the code and generic safe message only.
The normalizer converts Pydantic/JSON/semantic failures to these codes without
including payload, SDK exception text, source locator content, credentials, or
provider diagnostics. Existing Plugin finalization continues to ensure one
failed Stage and no successful Artifact on a post-start failure.

No database migration, Compose change, API route, or UI change is required.
The catalog extension is source-compatible, while Registry bootstrap changes
make the normalizer available to later Profile compilation. S-004 plans that
continue to use `opaque.bytes/v1` remain valid. Later Chunk/Evidence consumers
must deserialize `canonical.document/v1` through these contracts and refer to
element IDs/locators; they must not inspect a provider Artifact.

## Alternatives And Risks

- A loose dictionary contract would make provider data easy to retain but
  cannot enforce table spans, hierarchy, locator completeness, or bounded
  evolution. Strict typed variants implement the confirmed provider-neutral
  boundary.
- Storing Canonical structures in PostgreSQL would duplicate S-002 Artifact
  storage and make large document payloads part of trace records. JSON bytes
  in the existing content-addressed store preserve the established boundary.
- Accepting provider SDK models in the normalizer would be convenient for one
  adapter but would leak an unavailable dependency through Plugin contracts.
  The adapter payload is JSON bytes behind an Artifact reference instead.
- IDs based only on provider element IDs could change across provider retries
  or versions. Derivation from source digest and normalized structural position
  is reproducible, with the tradeoff that a changed source creates new IDs as
  intended for immutable lineage.

## Test Strategy

Add `tests/contract/test_canonical_document.py` for multi-kind Canonical
fixtures, deterministic byte serialization/round-trip, all locator variants,
table grid/header/caption/relationship validation, hierarchy/order validation,
safe error codes, extra-field rejection, and explicit size/count/string bounds.

Add `tests/contract/test_canonical_normalizer.py` with a representative typed
provider fixture containing headings, paragraphs, lists, figures, captions,
code, a table, metadata, provenance, quality signals, and all locator kinds.
Run it through the registered S-003 normalizer and assert golden bytes,
stable IDs across repeated invocations, typed output schema, and exact S-002
parent lineage. Parameterize malformed fixture cases for every AC-4 rejection.

Add an architecture/security regression that attempts to supply a non-JSON
provider SDK object and proves it cannot become a typed Plugin input or enter
Canonical models, persisted manifests, traces, or output bytes. Inspect the
normalizer result and trace summaries using provider/credential canaries to
prove redaction. Update trace-schema catalog assertions and Registry/Profile
tests to cover the new schema pairs and bootstrap descriptor while retaining
the current opaque-byte regression cases.

Run focused canonical, Plugin, Trace, and Ingestion Profile contract suites,
then the existing full test suite. Docker integration is not added because the
normalizer is an in-process, pure deterministic contract Plugin and S-002/S-003
already own persistence and cross-runner integration coverage.

## Implementation Checklist

- [ ] Add the strict Canonical, table, locator, provenance, quality, and
  provider-fixture contracts plus canonical serializer/ID derivation helpers.
- [ ] Extend the S-002 Artifact schema catalog and aligned safe error vocabularies.
- [ ] Implement and bootstrap `normalizer.canonical@1` through the existing
  S-003 Registry/Executor path.
- [ ] Add valid golden fixtures and invalid schema/semantic/bounds matrices.
- [ ] Add provider-boundary/security regression and update affected Plugin,
  Trace, and Profile catalog assertions.
- [ ] Run focused and full regression suites.

## Open Questions

None. Exact production Parser/OCR payload schemas, source-document ingestion,
and plan execution remain owned by S-006 and S-010; chunk representations and
consumer behavior remain owned by S-008 and later query Stories.

## Approval

Pipeline invocation authorizes this just-in-time technical design. It records
implementation choices only and does not change the confirmed Story contract.

## Change History

- **2026-09-11:** Created for the S-005 Story Pipeline delivery run.
