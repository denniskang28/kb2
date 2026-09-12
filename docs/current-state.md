# Current State

- **As Of:** 2026-09-12
- **Harness State:** Lite Harness Initialized
- **Product Requirements:** Approved - 2026-09-10 (17 confirmed REQs)
- **Core Design:** Approved - 2026-09-10 (16 confirmed DES records)
- **Feature Map:** Confirmed - 2026-09-10 (5 Features)
- **Feature Designs:** 3 Approved (FD-001 through FD-011)
- **UI Prototype Brief:** Ready - 2026-09-10
- **Claude Design Prompt:** Ready - 2026-09-10
- **UI Prototype / Reference:** Confirmed - 2026-09-11 (`UI-001` through
  `UI-013`)
- **Stories:** S-001 through S-023 Implemented; S-024 through S-027 Confirmed
- **Active Story:** None; S-024 is next eligible
- **Application/Test Baseline:** Python/FastAPI runtime, Docker Compose,
  PostgreSQL/pgvector, optional external DeepSeek capability boundary, Plugin
  Registry/Runner contracts, declarative Ingestion Profile compilation and
  deterministic resolution, CanonicalDocument/v1 normalization with typed
  cross-format locators and table semantics, reusable structure validation and
  preservation Plugins, deterministic citation-preserving ChunkSet/v1
  chunking and bounded enrichment Plugins, deterministic provider-neutral
  embedding and local hybrid index Artifacts with failure recovery,
  deterministic candidate fusion and optional reranking with preserved
  attribution and safe failures, deterministic citation-ready EvidenceSet/v1
  context assembly with bounded excerpts, traceable source locators, grounded
  external generation with validated final states and bounded repair, safe
  no-publication failures, deterministic answer, citation, and decision metrics
  with exact fact spans, strict Evidence identity, explicit applicability
  states, frozen decision cohorts, and bounded failure lineage, a
  Docker-backed Artifact trace persistence/restart regression, and an isolated
  lifecycle regression

## Current Boundary

Knowledge Engine Lite is scoped to a local experiment runtime, configurable
document ingestion, configurable evidence-grounded query execution, and
reproducible layered evaluation. Profiles compile declarative configuration to
resolved execution plans. Reusable allowlisted Plugins implement typed stages.
All parsing paths converge on a provider-neutral Canonical Document; query paths
converge on citation-ready Evidence and validated final states. Evaluation
separates ingestion, retrieval, answer, citation, abstention, latency, and local
resource results.

Enterprise identity, authorization, administration, publication, approval,
rollback, quota, file-size policy, retention, source connectors, managed Azure
services, and HA/DR are explicitly outside the Lite boundary. Internal digests,
revisions, lineage, and snapshots required to reproduce experiments do not
reintroduce user-facing version-management scope.

The project-level Codex agents, skills, Story Pipeline configuration, and lean
workflow were copied from `../kb` and adapted to this engine-first boundary.
S-001 establishes the local control API, worker heartbeat, PostgreSQL/pgvector,
Artifact-volume probe, scoped lifecycle CLI, capability readiness contract, and
optional external DeepSeek provider boundary. No ingestion/query/evaluation
domain engine or benchmark corpus has been established. FEAT-005 owns the thin
experiment workbench, and `docs/ui/reference.md` governs its adopted workbench
flows, diagnostic states, responsive behavior, and visual direction.

## Recommended Next Action

Deliver S-024 next for document, Ingestion Run, and Artifact inspection.
S-024 through S-027 are confirmed and may enter just-in-time technical design
when their declared dependencies are implemented.

## Change History

- **2026-09-10:** Initialized the Lite Harness, approved product/core design,
  and confirmed four Feature boundaries.
- **2026-09-10:** Approved three shared Feature designs covering FD-001 through
  FD-011.
- **2026-09-10:** Added FEAT-005 and prepared the external UI prototype brief
  and Claude Design prompt.
- **2026-09-10:** Compiled FEAT-001 into S-001 through S-003; all three await
  explicit Story boundary confirmation.
- **2026-09-10:** User confirmed S-001 through S-003; S-001 is next for
  delivery.
- **2026-09-10:** Started the S-001 Story Pipeline delivery run.
- **2026-09-11:** Implemented S-001 with a credential-independent local core
  runtime and optional external DeepSeek generation readiness; verification and
  final review passed.
- **2026-09-11:** Adopted the Claude Design workbench prototype as UI Reference
  v1 (`UI-001` through `UI-013`), with prototype data, implementation, locale
  switching, and stale fully offline claims excluded.
- **2026-09-11:** Compiled FEAT-002 through FEAT-005 into S-004 through S-027;
  all new Story boundaries remain `Needs Confirmation`.
- **2026-09-11:** User confirmed S-004 through S-027 Story boundaries; all are
  eligible for just-in-time design when their dependencies are satisfied.
- **2026-09-11:** S-002 implementation, Docker-backed persistence/restart
  verification, and final review passed; its delivery was merged into local
  main.
- **2026-09-11:** S-003 Plugin Registry and Runner implementation, cross-runner
  and deployed-sidecar verification, and final review passed; its delivery was
  fast-forwarded into local main.
- **2026-09-11:** S-004 Ingestion Profile compilation and deterministic
  resolution implementation, verification, and final review passed; ready for
  delivery close.
- **2026-09-11:** S-005 CanonicalDocument/v1 and typed normalizer boundary
  implementation, acceptance/regression verification, and repaired final
  review passed; delivery commit `d895b26` was fast-forwarded into local main.
- **2026-09-11:** S-006 representative parser and OCR Plugins implementation,
  repaired acceptance/regression verification, and final review passed;
  delivery commit `9afcd68` was fast-forwarded into local main.
- **2026-09-11:** S-007 reusable hierarchy, reading-order, and table
  preservation Plugins implementation, Artifact restart verification, and
  repaired final review passed; delivery commit `5bc3f7e` was fast-forwarded
  into local main.
- **2026-09-11:** S-008 citation-preserving ChunkSet/v1 chunking and bounded
  enrichment implementation, repaired acceptance/regression verification, and
  final review passed; delivery commit `5dc55e7` was fast-forwarded into local
  main.
- **2026-09-12:** S-009 deterministic provider-neutral embedding and local
  hybrid index Artifact implementation, repaired acceptance/regression
  verification, and final review passed; delivery commit `9c76031` was
  fast-forwarded into local main. Docker restart/readback verification remains
  environment-blocked because Compose startup stalled before creating
  containers.
- **2026-09-12:** S-010 completed bounded ordered Profile sub-stages under
  FD-012, pinned end-to-end ingestion execution, trace input/resolution
  persistence, restart evidence, and repaired final review; delivery commit
  `4ed5c6b` was fast-forwarded into local main.
- **2026-09-12:** S-011 completed declarative Query Profile compilation,
  deterministic selection, pinned Search Artifact plan identity, baseline
  query-family fixtures, independent verification, and repaired final review;
  delivery commit `9fc5eab` was fast-forwarded into local main.
- **2026-09-12:** S-012 completed provider-neutral independent keyword, vector,
  hierarchy, table, and metadata retrieval candidate sets, request-bound
  identity validation, safe retrieval failures, and replacement-provider
  conformance; independent verification and repaired final review passed.
- **2026-09-12:** S-013 completed deterministic reciprocal-rank candidate
  fusion, optional lexical-overlap reranking, repeated typed candidate ports,
  preserved contributor attribution, safe failure behavior, independent
  verification, and repaired final review; delivery commit `49ceee3` was
  fast-forwarded into local main.
- **2026-09-12:** S-014 completed deterministic citation-ready EvidenceSet/v1
  context assembly with bounded source excerpts, exact locator and Artifact
  lineage validation, explicit shortage outcomes, typed retrieval/fusion/rerank
  adapters, and safe no-publication failures; independent verification and
  final review passed; delivery commit `3c2bd16` was fast-forwarded into local
  main.
- **2026-09-12:** S-015 completed grounded DeepSeek generation, deterministic
  verification/final states, bounded same-Evidence repair, capability-pinned
  model configuration, and lineage-safe finalization. Independent verification
  and final review passed; delivery commit `8461e00` was fast-forwarded into
  local main and delivery-close reconciliation commit `86cef99` recorded the
  run evidence. Docker lifecycle tests remain environment-blocked by the known
  Compose startup stall.
- **2026-09-12:** S-016 completed versioned Golden Dataset contracts, explicit
  human-review provenance, controlled slice taxonomy, immutable evaluation
  snapshot Artifacts, and representative contract fixtures. Independent
  verification and final review passed; delivery commit `f70cb6a` was
  fast-forwarded into local main. The Docker-backed catalog/restart scenario
  is collected but remains environment-blocked by the known Compose startup
  stall before containers are created.
- **2026-09-12:** S-017 completed deterministic, independently registered
  ingestion quality metrics with per-document Artifact evidence, explicit
  missing-data states, taxonomy-aware slice aggregation, and traceable
  aggregation lineage. Independent verification and final review passed; the
  Docker lifecycle scenario remains environment-blocked by the known Compose
  startup stall.
- **2026-09-12:** S-018 completed deterministic retrieval/ranking and context
  metrics with exact citation-ready relevance resolution, independent
  keyword/vector/hierarchy/table/fusion/rerank/context attribution, explicit
  missing states, query-slice aggregation, and high-cardinality trace-safe
  reporting. Independent verification and final review passed; the Docker
  lifecycle scenario remains environment-blocked by the known Compose startup
  stall.
- **2026-09-12:** S-019 completed deterministic answer fact/forbidden-fact,
  citation, and final-state decision metrics with explicit missing-data states,
  frozen cohort membership, and bounded failed-case navigation. Independent
  verification and final review passed; Docker lifecycle coverage remains
  environment-blocked by the known Compose build/start stall before containers
  are created.
- **2026-09-12:** S-020 completed trusted Golden Dataset-derived calibration
  snapshots, bounded human-review provenance, provider-neutral Judge execution,
  pinned per-slice calibration and drift eligibility, and scoped unavailable
  provider failures. Independent non-Docker verification and final review
  passed; delivery commit `aa42a69` was fast-forwarded into local main.
- **2026-09-12:** S-021 completed pinned evaluation orchestration, layered
  reports, slice-aware gates, reproducible Profile comparison, failed-case
  navigation, and replay nondeterminism evidence. Independent non-Docker
  verification and final review passed; Docker lifecycle coverage remains
  unavailable due the known Compose startup limitation.
- **2026-09-12:** S-022 completed the FastAPI-served workbench shell and
  read-only runtime overview with bounded persisted Run/comparison projections,
  distinct core/provider/Plugin readiness, responsive accessible drawer
  navigation, and fixture-backed desktop/narrow visual verification. Delivery
  commit `3bdfd41` was fast-forwarded into local main. Full Docker lifecycle
  coverage remains environment-blocked by the known Compose startup stall.
- **2026-09-12:** S-023 completed Profile and Plugin Studio API-backed working
  configurations, server-owned compatibility, Registry inspection, responsive
  Studio/Registry workflows, and browser verification. Delivery commit
  `b8af610` was fast-forwarded into local main; Docker lifecycle coverage
  remains environment-blocked by the known Compose startup stall.
