# S-014: Evidence And Context Assembly

- **Parent Feature:** FEAT-003
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-005, S-008, S-012, S-013

## Outcome

Assemble bounded, citation-ready `EvidenceSet/v1` context while preserving exact
source locators and explaining why candidates entered or left the context.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-010`, `REQ-011` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-011` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-003-configurable-query-engine.md#FD-006` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-003-configurable-query-engine.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Evidence identifies citation key, document, Chunk, Canonical elements,
  format-specific locator, bounded excerpt, contributors, and safe scores.
  `[DES-011][FD-006]`
- Context may apply deduplication, parent/neighbor expansion, diversity,
  structure rules, and token/item bounds only as declared by Profile. `[FD-006]`
- Table Evidence can include a bounded rendered region and exact table/cell or
  sheet/range identity. `[FD-006]`
- Internal vectors and unbounded provider payloads are excluded. `[DES-011]`

## Scope

- `EvidenceSet/v1`, Evidence item, citation mapping, and context-decision
  contracts.
- Deterministic context assembly with declared budgets and inclusion/exclusion
  rationale over ranked candidates.
- Exact source resolution back to Canonical and Artifact lineage.

## Non-goals

- Answer generation, UI rendering, authorization policy, or silently widening
  context beyond the resolved Query plan.

## Acceptance Criteria

1. Every selected Evidence item has a stable unique citation key and resolvable
   document, Chunk, Canonical element, locator, excerpt, and lineage mapping.
2. Context budgets and structural rules produce deterministic decisions for
   fixed inputs and record included, excluded, expanded, and deduplicated items.
3. Prose, hierarchy, and table fixtures retain the exact source identity needed
   for answer-visible citations and source preview.
4. Missing/broken locators, unbounded excerpts, duplicate citation keys, or
   incompatible Artifacts fail validation before generation.
5. Evidence shortage is explicit and available to final-state validation; it
   never triggers undeclared retrieval or general-knowledge context.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-4 | Evidence/context golden and invalid fixtures | Contract |
| 2, 5 | Budget, expansion, shortage, and determinism scenarios | Integration |

## Open Questions

None. Exact budgets and expansion strategies require Story design and later
calibration.

## Relationships And Blocks

- Enables S-015, context metrics, citations, and FEAT-005 Evidence inspection.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-003 sources.
- **2026-09-11:** Story boundary confirmed by the user.
