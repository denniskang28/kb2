# Knowledge Engine Lite Harness Instructions

## Start Here

Read `docs/current-state.md` first. Then read only the target artifact and its
exact source anchors. Historical material is not default context.

## Core Model

```text
approved product requirements (REQ)
+ selective confirmed core design (DES)
+ optional adopted UI references (UI)
+ optional shared Feature design (FD)
                    -> self-contained Story contract
                    -> Story technical design
                    -> code -> test -> review
```

Chat memory is never the sole contract. Suggestions are not accepted facts
until the user confirms them.

## Product Boundary

The product is an engine workbench, not a general knowledge-management suite.
Its primary domains are:

- reusable ingestion plugins composed by declarative Profiles;
- a typed Canonical Document and traceable processing artifacts;
- configurable retrieval, reranking, context, generation, and verification;
- reproducible datasets, metrics, quality gates, and Profile comparison;
- a local experiment runtime and thin operator console.

Do not introduce identity administration, approval/publication workflows,
tenant governance, quota, file-size policy, retention, HA/DR, or Azure-specific
behavior without an explicit product-scope change.

## Source Ownership

- `docs/prd.md`: confirmed product scope and observable requirements.
- `docs/core-design.md`: selected confirmed cross-Story design records.
- `docs/feature-map.md`: Feature routing and dependency overview.
- `docs/features/`: lean Feature routing manifests.
- `docs/designs/features/`: optional shared Feature design only.
- `docs/stories/`: self-contained delivery contracts.
- `docs/designs/stories/`: just-in-time Story technical designs.
- `docs/run-logs/`: Story Pipeline execution evidence.

Do not create empty owner documents. Add optional design or UI artifacts only
when confirmed content needs them.

## Workflow Gates

- Product requirements require explicit approval before Feature mapping.
- Core Design is selective; only confirmed DES items are authoritative.
- A Feature boundary must be confirmed before Story decomposition.
- A Story must be confirmed, self-contained, current, and unblocked before
  technical design or coding.
- Code must satisfy Story acceptance criteria, focused tests, regression tests,
  and review before completion.
- Internal run/profile/plugin identifiers required for reproducibility are not
  user-facing version-management scope.

## Commands

- Analyze or revise global scope: `requirements-agent`
- Map approved scope to Features: `$feature-mapping`
- Optionally design shared Feature behavior: `feature-design-agent FEAT-###`
- Compile a Feature into Stories: `$feature-to-stories FEAT-###`
- Deliver a Story: `story-pipeline-agent S-###`
- Classify a change: `$change-triage`
- Audit readiness and provenance: `$harness-audit [target]`

## Safety And Reproducibility

- A Profile is declarative data and must never contain an arbitrary shell
  command, filesystem script path, credential, or executable code.
- Runtime implementations are selected only through an allowlisted Plugin
  Registry with typed input/output contracts.
- Do not commit proprietary documents, credentials, private endpoints, model
  weights, or unredacted evaluation traces.
- Every benchmark must identify its dataset, inputs, execution plan, plugins,
  models, prompts, and result artifacts sufficiently for reproduction.

## Current Boundary

The PRD, Core Design, and four Feature boundaries are confirmed. No Stories,
application code, test baseline, or UI reference exists yet.
