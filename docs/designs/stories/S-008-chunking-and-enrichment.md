# Story Design: S-008 - Chunking And Enrichment Components

## Status

Approved

## Story Contract Snapshot

- Story: `docs/stories/S-008-chunking-and-enrichment.md`
- Confirmed Version Or Date: Confirmed 2026-09-11
- Material Decisions Requiring Approval: None. The Story Pipeline invocation
  authorizes these implementation choices.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Define frozen `ChunkSet/v1`, `Chunk`, citation, parent/child, and enrichment-provenance contracts. Derive deterministic chunk IDs from the document identity, strategy/configuration, ordered source element IDs, and canonical rendered content. The executor persists the ChunkSet as a child of the Canonical Artifact. | Contract tests assert schema validity, deterministic IDs and bytes, bounded content/token counts, element IDs, source locators, relations, and parent Artifact lineage. |
| 2 | Implement fixed-window, parent-child, hierarchy-aware, and table-aware modes in the same registered chunker selected by closed Profile configuration. Render Canonical prose/list/table data only from the validated Canonical Document and retain exact citation sources. | Golden fixture tests cover long hierarchy, prose boundaries, and merged-header table output; Profile integration compiles and invokes each strategy through one descriptor. |
| 3 | Add a separate enrichment Plugin which validates a bounded allowlisted metadata patch, creates provenance records per field, and merges only into the ChunkSet's enrichment namespace. It may not alter document ID, chunk IDs, source element/locator citations, parent links, or Canonical-derived identity fields. | Contract tests cover accepted bounded fields/provenance and reject undeclared fields, oversized values, duplicate/conflicting field provenance, and attempts to overwrite authoritative fields. |
| 4 | Validate source-element existence, locator equivalence, content and token/item limits, unique IDs, acyclic/in-document parent links, and authoritative identity invariants before emitting output. Map violations to bounded Plugin errors, quality signals, and no Artifact commit. | Invalid-reference, missing-locator, cyclic-parent, excessive-content, and malformed-ChunkSet scenarios assert actionable safe error codes/signals and no downstream Artifact. |
| 5 | Register the chunker and enricher through existing Plugin Registry descriptors with named `canonical_document` / `chunk_set` ports and frozen configuration schemas; consume them solely through Profile candidates. | Architecture integration registers a second compatible synthetic chunker or enricher, selects it only in a Profile fixture, and proves no compiler/resolver/executor dispatch change is required. |

## Current Code Findings

`CanonicalDocument/v1` already provides immutable document and element IDs,
typed locators, ordered hierarchy, language, metadata, and exact table cells,
captions, and relationships. `S-007` validates and preserves those fields in a
new Canonical Artifact; its output is the sole input shape for chunking.

The Registry, Executor, and Artifact service already validate named ports,
configuration schemas, byte limits, immutable parent Artifact lineage, metrics,
quality signals, and safe failures. The Profile compiler already has distinct
`chunking` and `enrichment` axes, records ordered candidates/configuration in a
digestible resolved plan, and forbids schema-incompatible fallbacks. The closed
Artifact catalog currently ends at `canonical.document/v1`, so `chunk.set/v1`
must be added before either descriptor can register. Runtime evaluation of
resolved candidates remains owned by S-010.

## Proposed Approach

### Contracts And Artifact Boundary

Add `kb2_runtime.chunking` with frozen Pydantic contracts and deterministic
JSON serialization:

```text
chunking/
  contracts.py     # ChunkSet/v1, citations, enrichment fields/provenance, bounds
  renderer.py      # Canonical element/table-to-text rendering and token estimate
  processor.py     # strategies, validation, deterministic identity construction
  plugin.py        # chunker and enricher PluginContext adapters
```

`ChunkSet/v1` contains a source `document_id`, document metadata/language
snapshot, and ordered unique Chunks. A Chunk contains its stable `chunk_id`,
bounded rendered content, deterministic whitespace-token count, ordered source
element IDs, one-or-more exact source locators, optional parent chunk ID,
bounded child chunk IDs, hierarchy context, language, and an enrichment map.
Each enrichment value carries its producer Plugin ID, configuration digest, and
the source chunk ID; the fields remain bounded JSON primitives or short lists
of primitives. No provider-native payload is accepted or serialized.

The chunk ID is a prefixed SHA-256 digest over the schema version, Canonical
document ID, chunk strategy/configuration, ordered source element IDs, parent
chunk ID (when present), and the canonical rendered content. It is computed
after rendering and cannot be supplied by Plugin configuration. The serializer
sorts object keys and keeps tuple order, making equivalent input/configuration
produce equivalent ChunkSet bytes and identities. Its Artifact parent is the
single input Canonical Artifact, preserving the full S-002/S-007 lineage.

Extend `trace.schemas.SUPPORTED_ARTIFACT_SCHEMAS` with
`("chunk.set", "v1")`. This is an additive in-memory Artifact schema
allowlist change only; no database migration, API route, or Compose change is
required.

### Chunker Strategies

Register `chunker.canonical@1` as an in-process Plugin:

```text
canonical.document/v1 -> chunk.set/v1
input port: canonical_document
output port: chunk_set
configuration: strategy, max_tokens, overlap_tokens, max_children
strategies: fixed_window | parent_child | hierarchy | table
```

Configuration is frozen and extra-forbidden. Initial calibrated limits are
`max_tokens` 64 through 512 (default 256), `overlap_tokens` 0 through 64 and
strictly less than `max_tokens`, and `max_children` 1 through 64 (default 32).
The deterministic token estimate is normalized whitespace-delimited text; it
is a reproducible guardrail, not a model tokenizer claim. Content is capped by
the existing Canonical/Plugin bounds and each Chunk may cite at most 128
elements/locators.

All modes first validate and render the Canonical Document. Prose rendering
uses heading/paragraph/caption/code text and list items in reading order;
table rendering preserves caption, ordered header labels, row/column position,
and cell text without flattening away merged-span semantics. Every rendered
segment retains its contributing element IDs and locators.

- `fixed_window` groups contiguous rendered prose segments up to `max_tokens`,
  then carries the last whole segments whose tokens fit `overlap_tokens` into
  the next window. It never splits an element or table-cell rendering.
- `parent_child` first emits bounded child windows, then creates bounded parent
  chunks for contiguous child groups. Parent chunks cite the union of their
  children and reciprocal links must agree. A group that cannot fit within
  limits fails rather than emitting an unbounded parent.
- `hierarchy` starts a chunk at each heading scope and groups descendants in
  reading order. It preserves the heading path as hierarchy context; oversized
  scopes split using fixed-window rules while retaining that context.
- `table` emits each Canonical table as a citation-preserving unit when it fits;
  otherwise it repeats the caption/header representation with bounded row
  groups, while every chunk cites the table element and its exact table locator.
  Non-table content uses fixed-window grouping under this strategy.

The processor rejects an input that cannot produce a bounded chunk from one
rendered element or required table header/row group. It never truncates
silently, invents locators, accepts stale element IDs, or falls back to another
strategy.

### Enrichment And Merge Rules

Register `enricher.chunk-metadata@1` as a separate in-process Plugin:

```text
chunk.set/v1 -> chunk.set/v1
input port: chunk_set
output port: enriched_chunk_set
configuration: fields
```

`fields` is a bounded mapping of explicitly configured field names to literal
values applied to all chunks. Names use a restricted label syntax and values
are bounded JSON primitives or short primitive lists. This representative
enricher establishes the component boundary without arbitrary extraction or
model/provider calls. For each inserted field it records its own Plugin ID and
configuration digest in field provenance. Existing enrichment fields are
immutable: duplicate names fail rather than applying precedence or overwrite
rules. The Plugin first revalidates the full ChunkSet and recomputes expected
chunk IDs before adding fields, proving enrichment has not severed citation or
Artifact lineage.

Both plugins emit bounded metrics: `chunks_emitted`, `chunk_tokens_total`,
`chunk_parent_links`, `chunk_table_groups`, and `enrichment_fields_added` as
applicable. Quality signals are `chunk_validation` and `citation_validation`,
plus `enrichment_validation` for the enricher. Safe failure summaries mention
only the relevant stable error code and configuration label, never document
text, locator coordinates, or enrichment values.

### Profile And Extension Integration

No generic compiler or executor branch is introduced. Repository profile
fixtures bind `chunking` candidates to `chunker.canonical@1` and `enrichment`
candidates to `enricher.chunk-metadata@1`, using existing named-port and
schema checks. The enrichment input references `chunking.chunk_set` and its
output becomes `enrichment.enriched_chunk_set`; later S-009 can bind directly
to that compatible `chunk.set/v1` schema. Adding a replacement component
therefore requires a registered descriptor, compatible configuration/ports,
and Profile/tests only.

Candidate selection, fallback execution, and persistence of the
first-acceptable result remain S-010 responsibilities. Direct Plugin
invocation executes exactly one selected implementation.

## Relevant Impacts

### Data And Compatibility

`ChunkSet/v1` is a new immutable Artifact payload and the first downstream
Canonical consumer. It carries a narrow snapshot of only document/hierarchy/
language/metadata/citation information needed downstream. CanonicalDocument
and its serializer are unchanged. The `chunk.set/v1` schema is additive to the
artifact catalog; existing Artifacts and plans remain valid.

### Security And Observability

The initial plugins are deterministic, in-process, and have no filesystem,
network, subprocess, provider SDK, credential, executable, or arbitrary-code
configuration surface. Strict Pydantic schemas, configured value bounds, and
the existing executor output limit contain input/output size. Existing trace
Artifact manifests preserve producer/configuration digests and parent lineage;
the new safe metrics/signals diagnose eligibility without exposing content.

## Alternatives And Risks

- Separate plugins per chunking style would make initial modes individually
  simple but would multiply Profile components and conflict with the Story's
  reusable-component requirement. A closed strategy configuration supplies a
  consistent first implementation while preserving descriptor replacement.
- Model-tokenizer counts are not deterministic or locally available in this
  baseline. Whitespace tokens provide a stable bounded approximation; a later
  revisioned Plugin may use an allowlisted tokenizer if evaluation fixtures
  justify it.
- Retaining raw table cells as opaque metadata would hide exact evidence.
  Structured rendering keeps caption, headers, spans, row/column grouping, and
  table locator citations in the ChunkSet while avoiding provider payloads.
- Permitting enrichment overwrite precedence would make source and added data
  difficult to distinguish. Immutable additive fields with per-field
  provenance make conflicts explicit.

## Test Strategy

Add sanitized golden fixtures for prose, hierarchical, and table-heavy
Canonical Documents plus expected ChunkSet payloads. Contract coverage in
`tests/contract/test_chunking.py` exercises every strategy, deterministic
serialization/identity, exact citation preservation, bounds, parent/child
integrity, enrichment merging/provenance, malformed input, and no-commit safe
failure cases.

Add `tests/integration/test_chunking_profiles.py` to compile Profile fixtures
for the four strategies and separate enrichment axis, invoke selected
components, and assert shared descriptor/implementation use. It also registers
a compatible synthetic chunker/enricher solely in the test Profile to prove
the extension path needs no compiler/resolver/executor source changes. Run the
existing Canonical, Structure, Plugin, Profile, Trace, and full regression
suites. Docker-specific restart coverage is unnecessary because this Story
adds no persistence mechanism; the contract suite reparses canonical ChunkSet
bytes and established Artifact persistence coverage remains the regression
surface.

## Implementation Checklist

- [ ] Add frozen `ChunkSet/v1`, chunk citation/relation, enrichment provenance,
  and configuration contracts plus canonical serialization.
- [ ] Add the `chunk.set/v1` Artifact schema to the supported catalog.
- [ ] Implement bounded deterministic rendering, four reusable strategies,
  identity/relationship validation, and safe metric/signal output.
- [ ] Register the chunker and independently replaceable enricher through the
  existing Registry bootstrap without changing shared execution interfaces.
- [ ] Add sanitized golden/invalid fixtures and contract coverage for chunks,
  citations, bounds, enrichment, and eligibility failures.
- [ ] Add Profile/extension integration coverage and run focused plus full
  regression suites.

## Open Questions

None. Initial algorithm bounds and deterministic token approximation are
calibration choices authorized by the confirmed Story; S-009 owns embedding
tokenizer/provider behavior and S-010 owns resolved-plan execution.

## Approval

The Story Pipeline invocation authorizes this just-in-time technical design.
It records implementation choices only and does not change the confirmed Story
contract.

## Change History

- **2026-09-11:** Created for the S-008 Story Pipeline delivery run.
