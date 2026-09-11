# S-018: Retrieval And Context Quality Metrics

- **Parent Feature:** FEAT-004
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-012, S-013, S-014, S-016

## Outcome

Measure candidate retrieval and context selection separately so answer failures
can be traced to recall, ranking, fusion, reranking, or context decisions.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-013`, `REQ-015` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-010`, `DES-011`, `DES-014` | Confirmed 2026-09-10 |
| FD | `docs/designs/features/FEAT-004-reproducible-quality-evaluation.md#FD-009` | Approved 2026-09-10 |
| Feature | `docs/features/FEAT-004-reproducible-quality-evaluation.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Baseline retrieval metrics include Recall@K, MRR, NDCG@K, evidence hit rate,
  and context precision/recall. `[DES-014][FD-009]`
- Retriever, fusion, rerank, and context outputs retain separate candidates and
  decisions so metric attribution is not collapsed. `[DES-010]`
- Relevant labels resolve to citation-ready Evidence identities and locators.
  `[DES-011]`

## Scope

- Deterministic metric Plugins for retrieval/ranking and context selection.
- Per-case and per-contributor inputs, declared K, missing-data states, slices,
  sample counts, and trace links to candidate/Evidence Artifacts.

## Non-goals

- Answer semantics, hidden relevance judging, provider-specific scores, or one
  aggregate retrieval grade.

## Acceptance Criteria

1. Fixed ranked-list fixtures produce expected Recall@K, MRR, NDCG@K, and hit
   rate values with declared K and relevance semantics.
2. Context precision/recall measures selected Evidence separately from retrieval
   candidates and preserves inclusion/exclusion attribution.
3. Keyword, vector, hierarchy, table, fusion, and rerank results remain
   independently inspectable where the plan contains those stages.
4. Missing relevance labels, empty applicable sets, and inapplicable strategies
   produce explicit states rather than zero or omission.
5. Metrics aggregate by document/question slices with sample count and exact
   links back to failed cases and stage Artifacts.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-4 | Ranking/context golden and edge-case fixtures | Unit and contract |
| 3, 5 | Multi-stage attribution and slice scenario | Integration |

## Open Questions

None. Relevance grading and K values belong to Story design/dataset calibration.

## Relationships And Blocks

- Enables S-021 reports and retrieval/context diagnosis.

## Change History

- **2026-09-11:** Compiled from confirmed FEAT-004 sources.
- **2026-09-11:** Story boundary confirmed by the user.
