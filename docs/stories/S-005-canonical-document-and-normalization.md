# S-005: Canonical Document And Normalization Boundary

- **Parent Feature:** FEAT-002
- **Status:** Implemented
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-002, S-003

## Outcome

Give all parser paths one provider-neutral `CanonicalDocument/v1` contract that
preserves the structure and source identity required by retrieval and quality
evaluation.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-003`, `REQ-006`, `REQ-008` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-004`, `DES-005` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-002-configurable-ingestion-engine.md#FD-003` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-002-configurable-ingestion-engine.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Provider parse/OCR outputs remain typed diagnostic Artifacts; only a
  normalizer converts them to `CanonicalDocument/v1`. `[DES-004][FD-003]`
- Canonical content preserves ordered elements, hierarchy, reading order,
  tables, provenance, quality signals, and stable format-specific locators.
  `[REQ-006][DES-005]`
- Tables retain rows, columns, cells, spans, headers, captions, relationships,
  and exact source locations. `[DES-005]`
- A field enters v1 only when a representative fixture or downstream query,
  citation, or evaluation consumer justifies it. `[FD-003]`

## Scope

- Versioned Canonical Document, element, table, locator, provenance, and quality
  schemas with validation and deterministic serialization.
- Normalizer Plugin contract and at least one provider-output fixture converted
  without leaking provider SDK objects downstream.
- Stable element identities and Artifact lineage suitable for later Chunks and
  Evidence.

## Non-goals

- Production format parsers, OCR engines, structure inference, chunking,
  indexing, or visual rendering.
- Speculative universal document fields or provider-native payload exposure.

## Acceptance Criteria

1. Schema-valid fixtures represent paragraphs, headings, lists, figures,
   captions, code, hierarchy, reading order, tables, metadata, and quality.
2. PDF, presentation, spreadsheet, HTML, and word-processing locator variants
   are validated without losing their format-specific coordinates or anchors.
3. Normalization produces stable element IDs, ordering, provenance, and parent
   Artifact lineage from typed provider output.
4. Invalid table spans, duplicate IDs, broken hierarchy, missing locators, or
   unbounded provider fields are rejected with actionable safe errors.
5. Downstream contract fixtures consume only `CanonicalDocument/v1` and never a
   provider object.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-2 | Multi-format schema fixtures | Contract |
| 3-4 | Normalization golden files and invalid matrix | Unit and contract |
| 5 | Provider-boundary dependency test | Architecture regression |

## Open Questions

None. Exact physical representation is selected in Story design.

## Relationships And Blocks

- Depends on S-002 typed Artifact storage and S-003 normalizer invocation.
- Enables S-006 through S-009, FEAT-003 Evidence, and FEAT-004 metrics.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-002 sources.
- **2026-09-11:** Story boundary confirmed by the user.
