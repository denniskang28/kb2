# S-025: Query Lab And Evidence UI

- **Parent Feature:** FEAT-005
- **Status:** Implemented
- **Phase:** Lite Core
- **Priority:** P1
- **Dependencies:** S-015, S-022, S-024

## Outcome

Let engineers run a Query Profile and diagnose retrieval through final answer
with exact Evidence, citations, and source synchronization.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-017` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-009` through `DES-012`, `DES-016` | Confirmed through 2026-09-11 |
| FD | `docs/designs/features/FEAT-003-configurable-query-engine.md#FD-005` through `FD-007` | Approved 2026-09-10 |
| UI | `docs/ui/reference.md#UI-005`, `UI-008`, `UI-013` | Confirmed 2026-09-11 |
| Feature | `docs/features/FEAT-005-knowledge-engine-experiment-workbench.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- The UI renders resolved Query plans and bounded trace/Evidence returned by the
  engine; it performs no retrieval, scoring, or verification. `[FEAT-005]`
- Candidate lists remain separate through retrieval, fusion, rerank, and context
  decisions. `[DES-010][UI-008]`
- Final states use `ANSWERED`, `CLARIFICATION_REQUIRED`, `ABSTAINED`, or
  `FAILED`; repair and verification remain trace detail. `[DES-012][UI-008]`
- DeepSeek readiness and external-call boundary are shown when generation is
  selected. `[DES-016]`

## Relevant UI Reference

- Query Lab: `isQuery` route at archive entry line 778.
- Shared Artifact source inspector: `artOpen` line 1451.
- Shared visual language: `UI-013`.

## Scope

- Question/Profile controls, indexed Artifact selection, run/cancel, resolved
  plan/timing, candidate tabs, fusion/rerank/context decisions, final result,
  Evidence list, citations, and source preview.
- Adopted high-precision, table, hierarchy, ambiguous, unanswerable,
  verification-failed, repairing, and failure states using non-binding fixtures.

## Non-goals

- Chat history, browser query logic, adopting synthetic scores/model IDs,
  unsupported answer fallbacks, or raw vector display.

## Acceptance Criteria

1. A query selects only eligible indexed Artifacts and a valid Query Profile;
   run/cancel state follows the control API and capability readiness.
2. Resolved stages and timings render in order, with per-retriever candidates
   kept separate before fusion/rerank/context decisions.
3. Evidence shows citation key, excerpt, source, locator, contributors, bounded
   scores, context decision, and rationale; citations open synchronized source.
4. Final-state views exactly represent supported, clarification, abstention,
   provider failure, verification failure, and bounded repair outcomes.
5. No answer appears as supported when required Evidence/citation validation is
   missing; external generation boundaries are visible before execution.
6. Desktop and narrow screenshots preserve the three-part control, evidence,
   and answer hierarchy with dense tables and no overlapping content.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-5 | Query-state, citation/source, capability, and accessibility tests | Integration and end-to-end |
| 6 | Scenario screenshots and overflow checks | Visual regression |

## Visual Acceptance Matrix

| AC | UI Anchor | Viewport Or Context | State | Visual Expectation | Evidence |
|---|---|---|---|---|---|
| 2-6 | UI-008 | 1440 x 900 | Factual, table, hierarchy, ambiguous, unanswerable, verify failed, repairing, failed | Controls, stage trace, candidate decisions, answer, and Evidence remain visually distinct | State screenshots |
| 3, 6 | UI-005 | Desktop and narrow below 900 px, observed around 644 px | Citation source open | Inspector synchronizes selected Evidence locator and source | Screenshots and interaction recording |
| 6 | UI-008 | Narrow context above | Long question/evidence and all final states | Content reflows or scrolls without overlap; controls remain reachable | State screenshots and overflow check |
| 6 | UI-013 | Desktop and narrow contexts above | Interactive/status states | Adopted typography, rules, icons, focus, and semantic colors | Screenshot comparison |

## Open Questions

None. Exact query controls and renderer integration belong to Story design.

## Relationships And Blocks

- Depends on completed Query engine contracts and S-024 Artifact Inspector.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-005 and UI Reference sources.
- **2026-09-11:** Story boundary confirmed by the user.
- **2026-09-14:** Completed a UI-reference parity repair with production-typed
  candidate projections, Evidence-to-Context synchronization, authoritative
  final-state behavior, async stale-response protection, and eight reviewed
  desktop/narrow visual baselines.
