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

Not yet decomposed. Suggested boundaries: Golden Dataset contract/review;
ingestion metrics; retrieval/context metrics; answer/citation/abstention
metrics; judge calibration; reproducible comparison and report.

## Open Boundary Questions

None. Shared behavior is confirmed in
`docs/designs/features/FEAT-004-reproducible-quality-evaluation.md`.

## Change History

- **2026-09-10:** Created and confirmed the Feature boundary.
