# S-027: Comparison And Cross-Run Diagnosis UI

- **Parent Feature:** FEAT-005
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P1
- **Dependencies:** S-021, S-022, S-024, S-025, S-026

## Outcome

Let engineers compare pinned experiments and navigate unified Run history into
the exact stage and evidence responsible for a regression or failure.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-017` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-008`, `DES-015` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-004-reproducible-quality-evaluation.md#FD-011` | Approved 2026-09-10 |
| UI | `docs/ui/reference.md#UI-011`, `UI-012`, `UI-013` | Confirmed 2026-09-11 |
| Feature | `docs/features/FEAT-005-knowledge-engine-experiment-workbench.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Comparison and Run views render pinned API manifests and traces; the browser
  does not recompute metrics or infer causality. `[FEAT-005]`
- Quality, latency, and resources remain separate, and hard slices cannot be
  hidden by averages. `[DES-015]`
- Single-axis is the default; multi-axis comparisons are explicitly non-causal.
  `[DES-015][UI-011]`
- Recovery controls appear only when the Run contract permits them and preserve
  immutable plans and attempts. `[DES-008][UI-012]`

## Relevant UI Reference

- Comparison: `isCompare` route at archive entry line 1202.
- Unified Runs: `isRuns` route at line 717.
- Shared visual language: `UI-013`.

## Scope

- Baseline/candidate selection from eligible Runs, pinned manifest, metric/slice
  table, deltas, samples/confidence where provided, gates, cases, latency,
  resources, and non-mutating recommendation.
- Filterable mixed Run history, persistent filters/selection, Trace and Artifact
  navigation, and contract-permitted recovery.

## Non-goals

- Automatic activation, browser causal inference, one composite rank, arbitrary
  reruns, publication history, or adopting synthetic deltas and thresholds.

## Acceptance Criteria

1. Only manifest-compatible Runs can be compared; incompatible selections show
   the engine-provided reason without manufacturing missing data.
2. Comparison displays baseline, candidate, absolute/relative deltas, sample or
   confidence context, gates, failed cases, latency, and resources separately.
3. Single-axis changes identify the varied component; multi-axis comparisons are
   visibly labelled non-causal and make no component attribution.
4. Unified Runs filter across ingestion, query, evaluation, comparison, and
   contract tests while preserving filter and selected-row state across routes.
5. Trace, Artifact, Evidence, and failed-case navigation resolves through shared
   inspectors, and recovery controls follow authoritative Run state.
6. Desktop and narrow screenshots preserve dense comparison/run tables, status,
   filters, and drilldown actions without clipping or incoherent overlap.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-5 | Compatibility, comparison, filter persistence, drilldown, accessibility tests | Integration and end-to-end |
| 6 | Reference-state screenshots and overflow checks | Visual regression |

## Visual Acceptance Matrix

| AC | UI Anchor | Viewport Or Context | State | Visual Expectation | Evidence |
|---|---|---|---|---|---|
| 1-3, 6 | UI-011 | 1440 x 900 | Single-axis and multi-axis comparison | Dense manifest/metric comparison with independent quality, latency, resources, and clear causal label | State screenshots |
| 4-6 | UI-012 | 1440 x 900 | Mixed filtered Runs and selected row | Stable dense table, filters, status, Trace, and recovery columns | State screenshots |
| 4-6 | UI-011, UI-012 | Narrow below 900 px; observed around 644 px | Long IDs/metrics and filters | Horizontal scroll/reflow preserves labels and reachable actions without overlap | Screenshots and overflow check |
| 6 | UI-013 | Desktop and narrow contexts above | Interactive/status states | Adopted typography, ruled layout, focus, icons, and semantic colors | Screenshot comparison |

## Open Questions

None. Table/chart implementation belongs to Story design.

## Relationships And Blocks

- Completes FEAT-005 UI decomposition and depends on shared inspectors/workflows.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-005 and UI Reference sources.
- **2026-09-11:** Story boundary confirmed by the user.
