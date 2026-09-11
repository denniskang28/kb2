# S-021: Evaluation Gates And Reproducible Comparison

- **Parent Feature:** FEAT-004
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-010, S-015, S-016, S-017, S-018, S-019, S-020

## Outcome

Run layered evaluation over a pinned experiment manifest, apply slice-aware
quality gates, and compare Profile candidates without hiding tradeoffs.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-013` through `REQ-016` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-014` through `DES-016` | Confirmed through 2026-09-11 |
| FD | `docs/designs/features/FEAT-004-reproducible-quality-evaluation.md#FD-010`, `FD-011` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-004-reproducible-quality-evaluation.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- A manifest pins dataset, sources, Artifacts, Ingestion and Query plans,
  Plugins, models, prompts, parameters, metric/Judge definitions, slices, gates,
  and runtime summary. `[REQ-014][FD-011]`
- Quality, latency, and local resources remain independent; no opaque aggregate
  rank or overall quality score is allowed. `[DES-014][DES-015]`
- Gates target metric, slice, sample rule, aggregation, and threshold; critical
  unsupported facts or citations may use zero tolerance. `[FD-010]`
- Single-axis comparison is the default; named multi-axis experiments are
  explicitly non-causal. `[DES-015]`

## Scope

- Evaluation Run orchestration, pinned manifest, metric execution, aggregation,
  gate results, layered report, failed-case links, and replay.
- Baseline/candidate comparison with absolute/relative delta, sample/confidence
  context where meaningful, latency, resources, slices, and recommendation.

## Non-goals

- Automatic Profile activation, invented thresholds, byte-identical LLM replay,
  Azure conformance claims, or collapsing results to one score.

## Acceptance Criteria

1. An Evaluation Run rejects an invalid/unreviewed dataset or incomplete
   manifest and otherwise persists every identity needed for reproduction.
2. Reports separate ingestion, retrieval, answer, citation, decision, latency,
   and resources and preserve explicit missing-data states.
3. Slice gates enforce sample and calibration eligibility; averages cannot mask
   a failed hard slice or zero-tolerance failure.
4. A comparison fixes inputs and shows baseline, candidate, deltas, cases,
   gates, latency, and resources without mutating either Profile.
5. Multi-axis comparison is labelled non-causal; single-axis changes identify
   the varied component explicitly.
6. Aggregate-to-case navigation resolves exact ingestion, retrieval, Evidence,
   generation, verification, metric, and Run artifacts.
7. Replaying a manifest reuses pinned inputs and reports environmental/model
   nondeterminism rather than claiming byte-identical generation.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-3 | Manifest, missing-state, gate, and calibration fixtures | Integration |
| 4-5, 7 | Single/multi-axis and replay scenarios | End-to-end |
| 6 | Cross-layer failed-case trace | Integration |

## Open Questions

None. Numerical thresholds and confidence methods require Story design and
calibration.

## Relationships And Blocks

- Completes FEAT-004 and enables evaluation/comparison UI Stories.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-004 sources.
- **2026-09-11:** Story boundary confirmed by the user.
