# S-010: Ingestion Engine Execution And Validation

- **Parent Feature:** FEAT-002
- **Status:** Implemented
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-004, S-005, S-006, S-007, S-008, S-009

## Outcome

Execute resolved Ingestion Profiles end to end for representative complex
documents with typed Artifacts, explicit recovery, and inspectable Run evidence.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-003` through `REQ-008` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-002`, `DES-004`, `DES-007`, `DES-008` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-002-configurable-ingestion-engine.md#FD-001` through `FD-004`, `FD-012` | Approved 2026-09-10; FD-012 confirmed 2026-09-12 |
| Feature | `docs/features/FEAT-002-configurable-ingestion-engine.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Runs execute the pinned compiled plan, not a mutable Profile. `[DES-002]`
- Stages validate typed outputs before downstream use and record state,
  Artifacts, metrics, quality, timing, and safe failures. `[REQ-007][DES-008]`
- Retry preserves the plan; fallback is declared and measurable; runtime failure
  never switches implementations silently. `[DES-007][FD-004]`
- The six component axes remain fixed, while each axis can declare bounded
  ordered fully typed sub-stages in the pinned plan. `[FD-012]`
- At least three materially different document classes must prove component
  reuse and Profile variation. `[REQ-008]`

## Scope

- Ingestion orchestration over the common executor, Registry, runner, Artifact,
  Run, and trace contracts.
- Conditional stage execution, declared fallback, cancellation, retry, restart
  inspection, and final output eligibility.
- End-to-end representative Profiles and sanitized fixtures demonstrating
  extension without engine modification.

## Non-goals

- Query behavior, evaluation thresholds, UI, production scheduling, arbitrary
  DAGs, or silent best-effort output.

## Acceptance Criteria

1. A submitted document and explicit or resolved Profile create one Run pinned
   to the complete plan and produce only schema-valid downstream Artifacts.
2. Conditional skips, selected fallbacks, retries, cancellation, stage failure,
   and output-validation failure are distinguishable in persisted trace.
3. Retry uses the same plan and records a new attempt; changing configuration or
   implementation creates a new Run.
4. At least three materially different complex-document classes complete using
   shared Plugins and different resolved Profiles.
5. A new synthetic document strategy is delivered through Plugin and Profile
   data without modifying orchestration source.
6. Every failed or successful run remains diagnosable after restart through
   stage inputs/outputs, timing, metrics, quality signals, and safe errors.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-3, 6 | Lifecycle, restart, retry, fallback, and failure scenarios | Integration |
| 4-5 | Representative corpus and extension demonstration | End-to-end |

## Open Questions

None. Fixture choices and resource bounds belong to Story design.

## Relationships And Blocks

- Completes the FEAT-002 engine path.
- Enables FEAT-003 indexed retrieval, FEAT-004 ingestion evaluation, and
  FEAT-005 Ingestion Lab.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-002 sources.
- **2026-09-11:** Story boundary confirmed by the user.
- **2026-09-12:** User confirmed the FD-012 Profile-plan correction required
  for explicit parser/normalizer and projector/indexer execution.
- **2026-09-12:** Implementation, independent verification, and repaired final
  review passed; ready for delivery close.
