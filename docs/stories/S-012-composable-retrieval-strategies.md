# S-012: Composable Retrieval Strategies

- **Parent Feature:** FEAT-003
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-003, S-008, S-009, S-011

## Outcome

Retrieve independently measurable candidate sets for text, vector, hierarchy,
table, and metadata needs through one typed provider-neutral contract.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-009`, `REQ-010` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-010`, `DES-016` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-003-configurable-query-engine.md#FD-005`, `FD-007` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-003-configurable-query-engine.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Keyword, vector, hierarchy-aware, table-aware, and metadata strategies remain
  independently selectable and measurable. `[DES-010]`
- Each retriever preserves its own ranked candidate list and safe scores before
  fusion so changes remain attributable. `[FD-005]`
- Provider adapters consume common indexed Artifacts and cannot leak native
  search payloads into engine contracts. `[DES-016]`

## Scope

- `RetrievalCandidateSet/v1` and candidate contract with document, Chunk,
  Canonical element, locator, contributor, rank, and bounded safe score fields.
- Representative local keyword and vector retrievers plus hierarchy and table
  behavior sufficient for baseline Profiles; metadata filtering where declared.
- Deterministic filtering, limits, timeout, cancellation, and trace output.

## Non-goals

- Fusion, reranking, context assembly, generation, Azure AI Search, or opaque
  provider score exposure.

## Acceptance Criteria

1. Every strategy emits schema-valid ranked candidates with stable source and
   lineage identity from the same indexed Artifact set.
2. Keyword and vector results remain separate, and hierarchy/table candidates
   retain the structural fields required by their strategy.
3. Filters, limits, and deterministic routing are pinned in the Query plan and
   visible in bounded trace evidence.
4. Timeout, cancellation, unavailable provider, malformed result, or stale
   index identity returns a safe failure without an eligible candidate set.
5. A synthetic replacement retriever passes the same contract suite without
   Query engine changes.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-3 | Fixed retrieval fixtures by strategy | Contract and integration |
| 4 | Failure/cancellation matrix | Resilience |
| 5 | Provider substitution fixture | Architecture regression |

## Open Questions

None. Algorithms and initial local providers belong to Story design.

## Relationships And Blocks

- Enables S-013, S-014, retrieval metrics, and Query Lab candidate inspection.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-003 sources.
- **2026-09-11:** Story boundary confirmed by the user.
