# FEAT-003: Configurable Query Engine

- **Status:** Mapped
- **Phase:** Lite Core
- **Optional Design:** Approved

## Outcome And Boundary

Let an engineer compose and compare query strategies appropriate to particular
document and question classes while producing one citation-ready Evidence
contract and a grounded, validated final response.

## Source Routing

- Requirements: `REQ-009` through `REQ-011`
- Core Design: `DES-001` through `DES-004`, `DES-009` through `DES-012`,
  `DES-014` through `DES-016`
- UI Reference: None

## Confirmed Shared Rules

- Query Profiles compose typed analysis, rewrite, routing, retrieval, fusion,
  reranking, context, generation, verification, repair, and abstention stages.
- Keyword, vector, hierarchy, table, fusion, reranking, and context stages
  remain independently measurable.
- Every retrieval path emits `EvidenceSet/v1` with stable source locators and
  citation keys.
- `ANSWERED` requires valid evidence and citations; evidence shortage does not
  silently fall back to unsupported model knowledge.

## Dependencies And Risks

- Depends on FEAT-001 execution contracts and FEAT-002 Canonical/chunk/index
  artifacts.
- A fully arbitrary Query DAG would increase orchestration complexity without
  proving retrieval value; branching remains bounded and typed.
- Query quality can be inflated by answer judges when retrieval failures are
  hidden; trace and metrics must preserve stage attribution.

## Story Index

| Story | Outcome | Primary Source Coverage | Status |
|---|---|---|---|
| S-011 | Query Profile compilation | REQ-009; FD-005, FD-007 | Confirmed |
| S-012 | Composable retrieval strategies | REQ-009, REQ-010; FD-005, FD-007 | Confirmed |
| S-013 | Candidate fusion and reranking | REQ-009, REQ-010; FD-005, FD-006 | Confirmed |
| S-014 | Citation-ready Evidence and context assembly | REQ-010, REQ-011; FD-006 | Confirmed |
| S-015 | DeepSeek-backed grounded generation and final states | REQ-009 through REQ-011; FD-005, FD-006 | Confirmed |

All routed REQ-009 through REQ-011 are compiled into at least one Story. Shared
Feature rules and non-goals apply to every Story above.

## Open Boundary Questions

None. Shared behavior is confirmed in
`docs/designs/features/FEAT-003-configurable-query-engine.md`.

## Change History

- **2026-09-10:** Created and confirmed the Feature boundary.
- **2026-09-11:** Compiled S-011 through S-015; Story boundaries await user
  confirmation.
- **2026-09-11:** User confirmed S-011 through S-015 Story boundaries.
