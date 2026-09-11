# Story Design: S-007 - Structure And Table Preservation

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-007-structure-and-table-preservation.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-11; pipeline delivery
  started 2026-09-11.
- **Material Decisions Requiring Approval:** None. The pipeline invocation
  authorizes the bounded strategies and fixture corpus below; they retain the
  confirmed Canonical and declarative-Profile boundaries.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add one allowlisted `structure.canonical@1` Plugin that accepts and emits `canonical.document/v1`. Its three closed strategies validate or deterministically derive hierarchy and reading order while preserving every element ID and locator. | Contract goldens assert identity/locator equality, deterministic order and hierarchy, and valid serialized output for hierarchy and layout inputs. |
| 2 | Reuse the existing typed table model; add a lossless table strategy that validates table-to-element linkage, grid coverage, spans, headers, captions, relationships, and locators before reserializing canonical bytes. | Table-heavy golden includes merged spans, multiple header cells, caption, related elements, and spreadsheet source range; it round-trips through Artifact storage and a new service instance. |
| 3 | Convert JSON/contract/semantic structure failures to the existing bounded Canonical Plugin errors; invalid input produces no output Artifact and the executor retains its safe failed-attempt evidence. | Invalid matrix covers malformed bytes, noncontiguous/ambiguous order, hierarchy cycles/invalid heading transitions, invalid table references/spans/headers, and asserts an actionable stable error code with no commit. |
| 4 | Use the one descriptor with profile-validated `strategy` configuration for long hierarchical, layout-rich, and table-heavy profiles. No MIME-specific plugin forks or orchestration branches are introduced. | Integration compiles three Profile variants, invokes the same registered Plugin on representative Canonical Artifacts, and proves configuration is the sole selected-component difference. |
| 5 | Profiles retain ordered candidates and `accept_quality` through the existing S-004 resolved plan. The structure Plugin reports a named `structure_validation` quality signal. It never invokes another implementation; S-010 will execute and persist first-acceptable candidate selection. | Integration asserts plan candidate order/configuration/acceptance policy and that successful and failed Plugin invocations expose the structure signal or safe failure without an implicit second invocation. |

## Current Code Findings

S-005 already supplies an immutable, extra-forbidden `CanonicalDocument/v1`
with stable element IDs, contiguous reading order, earlier-parent hierarchy,
format-specific locators, and lossless table cell/grid/header/caption/
relationship validation. The deterministic serializer is the only Canonical
payload writer. S-006 has registered Parser/OCR-to-Canonical paths and keeps
the provider payload outside Canonical Artifacts.

The closed Artifact catalog already accepts `canonical.document/v1`, and the
S-003 executor/Registry can register an in-process Plugin with that schema as
both input and output. S-004 already compiles ordered candidates, validates
closed configurations, preserves `accept_quality`, and rejects incompatible
fallback output schemas. It deliberately does not execute candidates; that
runtime ownership belongs to S-010.

## Proposed Approach

### Structure Plugin And Configuration

Add a focused `kb2_runtime.structure` package:

```text
kb2_runtime/structure/
  contracts.py  # frozen StructureConfig and bounded strategy-specific rules
  processor.py  # Canonical decoding, deterministic transformations, validation
  plugin.py     # PluginContext adapter and safe result/signal construction
```

Register one in-process descriptor in `plugins.bootstrap`:

```text
structure.canonical@1
  canonical.document/v1 -> canonical.document/v1
  input port: canonical_document
  output port: structured_document
  quality signals: structure_validation, hierarchy_validation,
                   reading_order_validation, table_validation
```

`StructureConfig` is frozen and extra-forbidden. It has a required closed
`strategy` enum: `hierarchy`, `layout`, or `table`. It contains no provider,
path, command, executable, credential, or generic rules map. The strategy is
selected in Profile data, not by MIME type and not by an implementation-local
fallback.

All strategies decode bounded UTF-8 JSON, validate it as `CanonicalDocument`,
and serialize only through `canonical_document_bytes`. They preserve top-level
document/provenance/metadata identity, every element ID, every locator, every
table ID/cell ID, and all existing source quality evidence. A successful
output is therefore a new immutable Artifact with the input Canonical Artifact
as its only parent, while its payload retains exact source references.

`hierarchy` derives missing parent links deterministically without overwriting
valid explicit links: a heading is parented to the nearest prior heading of a
lower level; non-heading narrative/list/figure/code/table/caption elements
without a parent are parented to the nearest prior heading. The processor uses
a bounded heading stack and rejects heading-level skips greater than one.
Existing valid explicit parents are preserved, including deliberately broader
source groupings. Root-level content is valid. It validates the resulting
document before output.

`layout` requires compatible PDF locators for its ordered elements and derives
reading order by `(page_number, y0, x0, original_reading_order)`. It rewrites
only the contiguous `reading_order` values and remaps no IDs, locators,
parent references, table references, or cell coordinates. It rejects a parent
which would no longer precede its child after ordering rather than silently
dropping the relationship. For other locator families, Profiles must select
the declared/hierarchy strategy; no cross-format heuristic is inferred.

`table` performs no heuristic reconstruction. It enforces the existing exact
table contract plus that a table element and its table locator agree, table
caption targets a `caption` element, and related IDs do not point to the table
element itself. It preserves merged spans and cell positions exactly. This
deliberately treats invalid/incomplete provider table claims as ineligible
Canonical input rather than manufacturing cells or headers.

### Evidence, Failure, And Fallback Boundary

On success the Plugin emits bounded counts for elements, hierarchy links, and
tables plus `PASS` quality signals for the validations performed. Decoder and
validation failures map to `CANONICAL_INPUT_INVALID`,
`CANONICAL_DOCUMENT_INVALID`, or `CANONICAL_FIELD_UNBOUNDED`, using only the
existing allowlisted Plugin error code and generic safe trace message.

S-007 proves that a compiled Profile records each structure candidate,
configuration, candidate order, and accepted quality outcomes. The selected
candidate, acceptance signal, and result become one persisted selection event
when S-010 executes that resolved plan. Introducing an executor or automatic
candidate switch here would duplicate S-010 and violate FD-004's explicit
first-acceptable runtime boundary. The structure Plugin itself makes exactly
one implementation attempt per invocation, so a failure cannot silently
switch implementations.

## Relevant Impacts

### Data And Compatibility

No Artifact schema, database migration, API route, Compose service, or UI
change is needed: the immutable Canonical artifact schema is reused. The
existing normalizer remains permitted to emit structurally valid Canonical
documents; S-007 creates a subsequent structured Artifact when a Profile
selects it. S-008 will consume the structured Canonical bytes and their
preserved element/locator/table identities without learning a new payload
format.

### Security And Observability

The Plugin is deterministic in-process code with no network, filesystem,
subprocess, provider SDK, or executable configuration surface. Input and
output use existing Canonical bounds and the Plugin output limit. Diagnostics
contain only strategy labels, bounded counts, stable error codes, and generic
validation summaries, never document text, source coordinates, raw provider
payloads, credentials, or host data.

## Alternatives And Risks

- A separate Plugin per document characteristic would make future strategies
  easy to name but would turn Profiles into MIME/department dispatch and copy
  common validation. One typed configuration preserves the reusable component
  axis required by the Story.
- Inferring tables from arbitrary layout geometry would appear more capable but
  cannot guarantee headers, merged cells, or exact provenance. This Story only
  preserves and validates explicit typed table structure.
- Reassigning stable element IDs after layout ordering would break references
  retained by table and downstream consumers. IDs remain immutable; only the
  ordering relationship may be normalized.
- Layout sorting assumes normalized PDF coordinate orientation. The strategy
  rejects unsupported locator mixtures rather than producing an unverifiable
  cross-format order. Presentation and spreadsheet-specific heuristics remain
  available as future revisioned strategy behavior when justified by fixtures.

## Test Strategy

Add `tests/fixtures/ingestion/` golden Canonical JSON fixtures for a long
hierarchical document, a multi-page PDF layout document, and a table-heavy
spreadsheet document. The table fixture includes a merged header span,
caption, relationships, and source-range locators. Fixtures remain sanitized,
deterministic, and free of proprietary text.

Add `tests/contract/test_structure.py` for byte-stable success fixtures,
identity/locator preservation, hierarchy derivation, PDF reading-order
normalization, table losslessness, restart deserialization, configuration
rejection, and a malformed/semantic/bounds failure matrix. Assert no output
Artifact commits after any failed invocation and safe error/quality evidence.

Add `tests/integration/test_structure_profiles.py` to register the Plugin,
compile three characteristic-oriented Profiles using different structure
configurations, invoke their chosen structure candidates, and assert shared
descriptor/implementation identity. Include a two-candidate declared fallback
plan and prove candidate ordering plus quality acceptance serialization; a
failing first direct invocation must not invoke candidate two. Keep broader
fallback execution/persistence coverage for S-010.

Run the focused Canonical, Plugin, Profile, adapter, and structure suites,
then the full regression suite. Docker coverage is unnecessary because this
adds a pure in-process Plugin and does not alter the established persisted
Artifact service; the restart contract test exercises reparse of stored bytes.

## Implementation Checklist

- [ ] Add frozen structure configuration and Canonical structure processing
  modules with bounded, deterministic hierarchy/layout/table strategies.
- [ ] Register `structure.canonical@1` against the existing Canonical schema
  pair and preserve the existing Registry/Executor/trace interfaces.
- [ ] Add sanitized hierarchical, layout-rich, and table-heavy Canonical
  fixtures, including merged spans/caption/relationship source provenance.
- [ ] Add contract coverage for valid, invalid, lossless, safe-failure, and
  restart cases.
- [ ] Add Profile integration proving three configurations reuse the shared
  Plugin and declared fallback never switches implicitly.
- [ ] Run focused and full regression suites.

## Open Questions

None. Candidate execution and persistence of first-acceptable selection are
intentionally reserved for S-010, as declared by its confirmed contract.

## Approval

Pipeline invocation authorizes this just-in-time technical design. It records
implementation choices only and does not change the confirmed Story contract.

## Change History

- **2026-09-11:** Created for the S-007 Story Pipeline delivery run.
