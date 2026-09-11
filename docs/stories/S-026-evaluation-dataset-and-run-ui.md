# S-026: Evaluation Dataset And Run UI

- **Parent Feature:** FEAT-005
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P1
- **Dependencies:** S-016, S-017, S-018, S-019, S-020, S-021, S-022, S-024

## Outcome

Let reviewers maintain trusted labels and inspect layered Evaluation Runs from
aggregate metrics through exact failed-case evidence.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-017` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-013`, `DES-014`, `DES-015` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-004-reproducible-quality-evaluation.md#FD-008` through `FD-011` | Approved 2026-09-10 |
| UI | `docs/ui/reference.md#UI-009`, `UI-010`, `UI-013` | Confirmed 2026-09-11 |
| Feature | `docs/features/FEAT-005-knowledge-engine-experiment-workbench.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Dataset validation, review state, metrics, applicability, calibration, and
  gates are engine-owned API results. `[FEAT-005]`
- Generated cases remain unreviewed until explicit review. `[DES-013][UI-009]`
- Metric layers remain separate; `NOT_APPLICABLE` and
  `INSUFFICIENT_LABELS` remain visible. `[DES-014][UI-010]`
- Uncalibrated Judge metrics are advisory and cannot close hard gates.
  `[FD-010][UI-010]`

## Relevant UI Reference

- Evaluation Dataset: `isEvalset` route at archive entry line 983.
- Evaluation Run: `isEvalrun` route at line 1075.
- Shared visual language: `UI-013`.

## Scope

- Document/query annotation list-detail editing, slices, validation, filters,
  review action, and first-use/invalid/incomplete states.
- Evaluation manifest, layer bands, metric/slice filters, gates, applicability,
  Judge calibration state, case drilldown, and Artifact/source navigation.

## Non-goals

- Browser metric computation, auto-review, one overall score, approval roles,
  or adopting prototype thresholds and metrics as configured defaults.

## Acceptance Criteria

1. Dataset forms preserve every engine schema field and review state, validate
   references, and require deliberate review for generated/draft cases.
2. Evaluation execution displays immutable manifest identity and API lifecycle,
   including invalid dataset and unavailable/uncalibrated Judge states.
3. Ingestion, retrieval, answer, citation, decision, latency, and resources are
   visually separate with sample/applicability information.
4. Filters and gate results cannot hide failed hard slices, insufficient samples,
   or ineligible Judge metrics.
5. Metric/case drilldown opens exact Run, stage, Artifact, Evidence, generation,
   verification, and source evidence available from the contracts.
6. Desktop and narrow screenshots cover editing and each adopted Evaluation Run
   state with stable dense hierarchy and no overlap.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-5 | Dataset/review, metric-state, gate, drilldown, accessibility tests | Integration and end-to-end |
| 6 | Reference-state screenshots and overflow checks | Visual regression |

## Visual Acceptance Matrix

| AC | UI Anchor | Viewport Or Context | State | Visual Expectation | Evidence |
|---|---|---|---|---|---|
| 1, 6 | UI-009 | 1440 x 900 and narrow below 900 px, observed around 644 px | Reviewed, draft, invalid, incomplete, empty | Dense list/detail editing with clear review/validation hierarchy | State screenshots |
| 2-6 | UI-010 | 1440 x 900 | Running, completed with failures, passed/failed gates, invalid dataset, Judge uncalibrated | Pinned manifest and separate metric/gate bands with drilldown | State screenshots |
| 3-6 | UI-010 | Narrow context above | Long metric/slice data | Tables scroll/reflow without hiding applicability or gates | Screenshots and overflow check |
| 6 | UI-013 | Desktop and narrow contexts above | Interactive/status states | Adopted density, typography, rules, focus, and semantic colors | Screenshot comparison |

## Open Questions

None. Form/chart libraries belong to Story design.

## Relationships And Blocks

- Enables S-027 comparison and cross-run diagnosis.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-005 and UI Reference sources.
- **2026-09-11:** Story boundary confirmed by the user.
