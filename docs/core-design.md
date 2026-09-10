# Core Design

## Status

- **State:** Approved
- **Approved On:** 2026-09-10
- **Scope:** Cross-Story contracts for the Lite Core

This document records only confirmed, high-value decisions. Detailed classes,
physical schemas, technology selections, and thresholds remain Story design
unless stated here.

### DES-001: Three-Engine Product Architecture

- **Type:** Architecture
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-001 through REQ-017

The product consists of an Ingestion Engine, Query Engine, and Evaluation
Engine sharing typed Profile, Plugin, Artifact, Evidence, and Trace contracts.
A thin local control API and experiment console may operate them but must not
absorb their domain logic. Enterprise governance and Azure integrations are
outside the Lite boundary.

### DES-002: Declarative Profiles Compile To Execution Plans

- **Type:** Architecture / Data
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-002 through REQ-004, REQ-009, REQ-014

Profiles are declarative JSON or YAML documents. Before execution, the engine
validates a Profile and resolves defaults, conditions, plugin references, and
parameters into one immutable execution-plan snapshot. Runs use the snapshot,
not a mutable Profile file. Profiles cannot contain shell commands, script
paths, embedded code, credentials, or unrestricted environment references.

The supported orchestration model is a typed stage pipeline with bounded
conditional branches and explicit fallback. The Lite product is not a generic
DAG/workflow engine.

### DES-003: Allowlisted Plugin Registry

- **Type:** API / Security
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-002, REQ-003, REQ-005, REQ-016

Each implementation is registered by a stable identifier such as
`parser.docling@1` or `chunker.parent-child@2`. Registry metadata declares the
plugin kind, runner, configuration schema, input/output Artifact schemas,
resource hints, timeout, and implementation identity. A Profile references
only registered identifiers.

Trusted lightweight plugins may run in process. Plugins with conflicting,
heavy, GPU, or model dependencies run behind an isolated local-container
runner. Both runner types implement the same invocation and result contract.

### DES-004: Typed Artifact Exchange

- **Type:** Data / API
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-003, REQ-005 through REQ-007, REQ-010, REQ-014

Stages exchange immutable Artifact references rather than provider SDK objects
or arbitrary Python objects. Every Artifact records:

- artifact type and schema revision;
- content digest and storage locator;
- producing run, stage, plugin, and configuration digest;
- parent Artifact references;
- safe metrics and quality signals.

Large content remains in the Artifact Store; stage messages and traces carry
references and bounded summaries.

### DES-005: Provider-Neutral Canonical Document

- **Type:** Data
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-006, REQ-008, REQ-010, REQ-013

All parser paths normalize into `CanonicalDocument/v1`. It contains document
metadata, ordered elements, hierarchy, tables, source locators, provenance,
and quality signals. Elements have stable IDs and types such as heading,
paragraph, list, table, figure, caption, and code. Tables retain rows, columns,
cells, spans, headers, captions, and relevant element relationships.

Format-appropriate locators are preserved: PDF page/region, presentation
slide/object, spreadsheet sheet/range, HTML path/anchor, and word-processing
heading/paragraph anchor. Downstream chunkers consume only this contract.

### DES-006: Component-Axis Profile Composition

- **Type:** Architecture / Algorithm
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-002, REQ-004, REQ-005, REQ-008

An Ingestion Profile composes independently reusable extraction, structure,
chunking, enrichment, embedding, and indexing components. Business labels such
as contract or policy do not automatically create a complete custom pipeline.
They add a component or configuration only when measured structure or retrieval
behavior differs.

This avoids the Cartesian product of formats, domains, languages, and query
strategies. The initial planning envelope is approximately 15-25 reusable
plugins and 5-8 base Profiles, not one script per document class or department.

### DES-007: Deterministic Profile Resolution

- **Type:** Algorithm
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-004, REQ-007, REQ-017

Profile selection precedence is:

1. an explicit Profile requested for an experiment;
2. an explicit document-class rule;
3. deterministic preflight feature rules;
4. the configured default Profile.

Resolution uses bounded observable features such as media type, page count,
scan ratio, table density, and layout signals. Any fallback candidates and
their acceptance conditions are declared in the Profile. A runtime failure
must not silently switch implementations.

### DES-008: Ingestion Stage And Run Semantics

- **Type:** Architecture / Operations
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-003, REQ-007, REQ-014

Each stage has a terminal result of `SUCCEEDED`, `FAILED`, or `SKIPPED`, plus
typed output Artifacts, metrics, quality signals, timing, and a structured safe
error. The engine validates outputs before making them available downstream.
Retries preserve the resolved execution plan and are visible in the Run Trace.

Internal execution-plan revisions, digests, and Artifact lineage exist solely
for reproducibility; they do not imply user-facing version-management scope.

### DES-009: Query Pipeline Contract

- **Type:** Architecture / API
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-009 through REQ-011, REQ-014

A Query Profile composes applicable typed stages from: analysis, rewrite,
route, retrieve, fuse, rerank, context assembly, generate, verify, repair, and
abstain. Each stage records bounded trace evidence. A Profile may omit stages
that do not serve its document/question class, but it cannot bypass the common
Evidence and final-response validation contracts.

### DES-010: Retrieval Strategies Remain Composable

- **Type:** Algorithm
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-009, REQ-010, REQ-013 through REQ-016

The retrieval layer supports independently measurable keyword, vector,
hierarchy-aware, table-aware, and metadata strategies. A Query Profile may
execute several retrievers, combine candidates through declared fusion, apply
an optional reranker, and assemble bounded context. Retrieval, fusion,
reranking, and context metrics remain separate so improvements can be
attributed to the correct stage.

### DES-011: Citation-Ready Evidence Contract

- **Type:** Data / API
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-010, REQ-011, REQ-013

All retrieval strategies emit a common `EvidenceSet/v1`. Each selected item
identifies its chunk, canonical elements, source document, source locator,
authorized excerpt, retrieval contributors, and stable citation key. Internal
vectors and unbounded provider payloads are excluded. Context assembly retains
the mapping from answer-visible citation keys back to exact source evidence.

### DES-012: Grounded Final-State Validation

- **Type:** Algorithm / API
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-011, REQ-013, REQ-015

The final query state is `ANSWERED`, `CLARIFICATION_REQUIRED`, `ABSTAINED`, or
`FAILED`. `ANSWERED` requires evidence and valid citations under the active
Query Profile. Verification may trigger a bounded, traceable repair attempt;
it must not silently add general-knowledge evidence. Insufficient or invalid
evidence produces clarification or abstention.

### DES-013: Reviewed Golden Dataset Contract

- **Type:** Data
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-012 through REQ-015

An evaluation case contains a question, classification slices, expected and
forbidden facts, relevant source/evidence labels, required citation locators,
answerability, and optional deterministic expected answer. Ground truth is
reviewed by a human. Generated cases may enter a review queue but never become
ground truth automatically.

### DES-014: Layered Accuracy Metrics

- **Type:** Algorithm / Quality
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-013, REQ-015

Evaluation reports separate layers:

- ingestion: text/OCR error, element detection, reading order, table structure,
  source-locator correctness, and downstream evidence preservation;
- retrieval: Recall@K, MRR, NDCG@K, evidence hit rate, and context
  precision/recall;
- answer: deterministic fact checks, correctness, completeness, groundedness,
  citation precision/recall, and answer/abstention classification quality;
- operations: stage latency and bounded local resource usage.

No opaque aggregate score may hide a failed hard requirement. LLM judges are
used only for non-deterministic criteria and must report calibration against a
reviewed human-labeled subset.

### DES-015: Reproducible Profile Comparison

- **Type:** Quality / Operations
- **Status:** Confirmed
- **Strength:** Binding Constraint
- **Applies To:** REQ-014, REQ-015

A comparison pins one dataset snapshot, input/artifact set, resolved Ingestion
and Query execution plans, plugin/model/prompt identities, and parameters.
Default experiments change one component axis at a time; named multi-axis
experiments are allowed but do not imply causal attribution. Results present
quality, latency, and resource metrics independently and slice them by document
and question classification.

Thresholds are configured per meaningful slice. Critical unsupported claims or
invalid citations may be zero-tolerance gates even when averages pass.

### DES-016: Local-First Provider Boundary

- **Type:** Technology / Architecture
- **Status:** Confirmed
- **Strength:** Preferred Direction
- **Applies To:** REQ-001, REQ-016, REQ-017

The first runtime uses local Artifact Storage, metadata/search storage, model
providers, and containerized processing plugins. Provider ports cover Artifact
Storage, parsing/OCR, embedding, search, reranking, and generation. Future
Azure adapters must satisfy the same contracts and evaluation suites; local
results are not evidence of Azure-specific compatibility or conformance.

Exact local databases, model runtimes, and initial provider implementations
remain Story design choices so they can be selected against development-machine
constraints and representative benchmarks.

## Open Design Questions

None block Story decomposition. Initial technology choices, exact schemas,
plugin packaging, Profile syntax, fixture corpus, and calibrated thresholds are
material Story-design decisions and must be recorded before implementation.

## Change History

- **2026-09-10:** Initialized DES-001 through DES-016 from the user-confirmed
  Lite architecture discussion.
