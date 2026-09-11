# S-019: Answer, Citation, And Decision Metrics

- **Parent Feature:** FEAT-004
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-015, S-016

## Outcome

Measure deterministic answer facts, grounding, citations, and answer-versus-
abstain decisions as distinct quality dimensions.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-013`, `REQ-015` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-012`, `DES-014` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-004-reproducible-quality-evaluation.md#FD-009` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-004-reproducible-quality-evaluation.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Answer metrics keep fact coverage/violations, correctness, completeness,
  groundedness, and citation precision/recall separate. `[DES-014][FD-009]`
- Decision metrics measure answer/abstention and ambiguity handling against
  reviewed answerability labels. `[FD-009]`
- Final-state and citation contracts from DES-012 are authoritative; invalid or
  unsupported citations cannot be hidden by fluent text. `[DES-012]`
- Deterministic checks take precedence wherever dataset labels permit.
  `[REQ-015]`

## Scope

- Deterministic fact, forbidden-fact, citation, and decision metric Plugins.
- Per-case metric evidence linked to response, verification, Evidence, and
  dataset labels with explicit applicability states.
- Interfaces for later calibrated semantic metrics without treating them as
  deterministic.

## Non-goals

- LLM Judge calibration, one overall answer score, model feedback, or automatic
  ground-truth edits.

## Acceptance Criteria

1. Expected and forbidden fact fixtures produce deterministic coverage and
   violation evidence linked to exact output spans where applicable.
2. Citation precision/recall resolves answer citations to required Evidence and
   locators; malformed, missing, or unsupported citations remain explicit.
3. Answerable, ambiguous, and unanswerable fixtures measure final-state decision
   precision/recall independently from answer text quality.
4. Missing labels or non-applicable metrics return explicit states and cannot
   contribute a hidden passing value.
5. A failed case navigates to generation output, verification result, Evidence,
   and contributing Query stages without duplicating unbounded payloads.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-4 | Fact/citation/decision golden fixtures | Unit and contract |
| 5 | Cross-layer trace-link scenario | Integration |

## Open Questions

None. Exact deterministic matchers belong to Story design.

## Relationships And Blocks

- Enables S-020 semantic judging and S-021 reports/gates.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-004 sources.
- **2026-09-11:** Story boundary confirmed by the user.
