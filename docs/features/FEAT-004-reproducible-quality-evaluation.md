# FEAT-004: Reproducible Quality Evaluation

- **Status:** Mapped
- **Phase:** Lite Core
- **Optional Design:** Approved

## Outcome And Boundary

Let engineers and reviewers maintain trusted evidence labels, measure the
ingestion/retrieval/answer layers separately, diagnose failed cases, and compare
Profile candidates reproducibly by quality, latency, and local resource usage.

## Source Routing

- Requirements: `REQ-012` through `REQ-016`
- Core Design: `DES-004`, `DES-005`, `DES-008` through `DES-016`
- UI Reference: None

## Confirmed Shared Rules

- Golden cases contain reviewed expected/forbidden facts, relevant evidence,
  required citations, answerability, and classification slices.
- Deterministic metrics take precedence; LLM judges are limited to criteria
  needing semantic judgment and require human-label calibration.
- Ingestion, retrieval, answer, citation, abstention, latency, and resource
  results remain separate.
- Comparisons pin datasets, Artifacts, resolved plans, plugins, models, prompts,
  and parameters; the default experiment changes one component axis.
- Hard failures and per-slice gates cannot be hidden by an average or aggregate
  score.

## Dependencies And Risks

- Depends on FEAT-001 run/artifact identity and FEAT-002/FEAT-003 stage outputs.
- Ground-truth creation is the principal quality bottleneck and must not be
  replaced by unreviewed synthetic labels.
- Ingestion ground truth for layout and tables requires format-specific
  annotation tools or fixtures.
- Judge drift and correlated model errors require periodic calibration reports.

## Story Index

| Story | Outcome | Primary Source Coverage | Status |
|---|---|---|---|
| S-016 | Golden Dataset and human review | REQ-012, REQ-015; FD-008 | Confirmed |
| S-017 | Ingestion quality metrics | REQ-013, REQ-015; FD-009 | Confirmed |
| S-018 | Retrieval and context metrics | REQ-013, REQ-015; FD-009 | Confirmed |
| S-019 | Answer, citation, and decision metrics | REQ-013, REQ-015; FD-009 | Confirmed |
| S-020 | Judge calibration and semantic metrics | REQ-015, REQ-016; FD-010 | Confirmed |
| S-021 | Evaluation gates and reproducible comparison | REQ-013 through REQ-016; FD-010, FD-011 | Confirmed |

All routed REQ-012 through REQ-016 are compiled into at least one Story. Shared
Feature rules and non-goals apply to every Story above.

## Open Boundary Questions

None. Shared behavior is confirmed in
`docs/designs/features/FEAT-004-reproducible-quality-evaluation.md`.

## Change History

- **2026-09-10:** Created and confirmed the Feature boundary.
- **2026-09-11:** Compiled S-016 through S-021; Story boundaries await user
  confirmation.
- **2026-09-11:** User confirmed S-016 through S-021 Story boundaries.
