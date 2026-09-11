# S-016: Golden Dataset And Human Review

- **Parent Feature:** FEAT-004
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-002, S-005, S-014

## Outcome

Give reviewers a reproducible Golden Dataset contract for trusted document and
query labels, with deliberate human review as the authority boundary.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-012`, `REQ-015` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-013` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-004-reproducible-quality-evaluation.md#FD-008` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-004-reproducible-quality-evaluation.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Document annotations and query cases are distinct but share controlled slice
  labels and immutable source/Artifact identity. `[FD-008]`
- Query cases capture question, expected and forbidden facts, relevant Evidence,
  required citations, answerability, and optional deterministic answer.
  `[REQ-012][DES-013]`
- Document labels may cover text/span, elements/order, tables/cells/spans,
  locators, and evidence preservation. `[FD-008]`
- Generated cases remain unreviewed and never overwrite ground truth.
  `[DES-013]`

## Scope

- Versioned dataset snapshot, document annotation, query case, slice taxonomy,
  validation, review-state, provenance, and import/export contracts.
- Initial slices for format, processing class, native/OCR, structure, language,
  question class, difficulty, and criticality.
- Explicit create/edit/validate/mark-reviewed operations and immutable snapshots
  used by evaluation Runs.

## Non-goals

- Approval workflow, user roles, synthetic auto-approval, proprietary fixtures,
  or metric implementation.

## Acceptance Criteria

1. Valid document and query labels round-trip with exact source/Evidence
   identity, controlled slices, provenance, reviewer state, and schema revision.
2. Missing required facts, invalid locators, contradictory answerability,
   unknown slices, or broken Evidence references prevent snapshot eligibility.
3. Draft and generated cases cannot be treated as reviewed without an explicit
   review operation recorded in dataset provenance.
4. An immutable dataset snapshot pins every eligible case and source identity;
   later edits create a distinct snapshot without mutating prior Runs.
5. Fixtures cover reviewed, draft, invalid, answerable, ambiguous, and
   unanswerable cases plus representative document annotations.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-3, 5 | Dataset schema and state-transition fixtures | Contract |
| 4 | Snapshot immutability and replay scenario | Integration |

## Open Questions

None. Exact storage and initial reviewed corpus belong to Story design.

## Relationships And Blocks

- Enables S-017 through S-021 and FEAT-005 evaluation editing.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-004 sources.
- **2026-09-11:** Story boundary confirmed by the user.
