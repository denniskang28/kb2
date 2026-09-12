# S-017: Ingestion Quality Metrics

- **Parent Feature:** FEAT-004
- **Status:** Implemented
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-007, S-008, S-010, S-016

## Outcome

Measure document understanding and evidence preservation independently from
retrieval or answer quality using deterministic metrics where labels permit.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-013`, `REQ-015` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-005`, `DES-014` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-004-reproducible-quality-evaluation.md#FD-009` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-004-reproducible-quality-evaluation.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Ingestion metrics cover applicable text/OCR error, element detection, reading
  order, table structure/cells, locator accuracy, and evidence preservation.
  `[DES-014][FD-009]`
- Metrics identify owner layer, required ground truth, direction, slices, and
  missing-data behavior and emit per document before aggregation. `[FD-009]`
- Undefined results remain `NOT_APPLICABLE` or `INSUFFICIENT_LABELS`; they never
  become zero or disappear. `[FD-009]`

## Scope

- Metric Plugin contracts and deterministic implementations for the applicable
  ingestion baseline metrics justified by reviewed fixtures.
- Per-document evidence, slice tags, aggregation inputs, timing, and links to
  producing ingestion Run and Artifacts.

## Non-goals

- Invented thresholds, a combined quality score, OCR/parser implementation, or
  semantic answer judging.

## Acceptance Criteria

1. Each metric validates required labels and inputs, emits per-document value or
   explicit missing-data state, and identifies method, direction, and owner.
2. Perfect, partial, failed, not-applicable, and insufficient-label fixtures
   produce deterministic expected results.
3. Text/OCR, element/order, table/cell, locator, and evidence-preservation
   failures remain separately attributable to exact Artifacts and stages.
4. Aggregation by declared slices retains sample count and cannot convert missing
   results into passing values.
5. Adding a deterministic ingestion metric requires a registered Metric Plugin
   and tests, not evaluator orchestration changes.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-4 | Metric golden, missing-data, and slice fixtures | Unit and contract |
| 5 | Metric extension fixture | Architecture regression |

## Open Questions

None. Formula variants and thresholds require Story design and calibration.

## Relationships And Blocks

- Enables S-021 layered reports and ingestion failure diagnosis.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-004 sources.
- **2026-09-11:** Story boundary confirmed by the user.
