# UI Reference

## Status And Source

- **State:** Confirmed
- **Confirmed On:** 2026-09-11
- **Prototype Path:** `docs/ui/kb_ui.zip`
- **Prototype Entry:** `Knowledge Engine Lite.dc.html`
- **Design System:** `_ds/modernist-cb710465-178f-48eb-a563-3421b8f155b3/`
- **Version:** UI Reference v1
- **Source SHA-256:**
  `a07df450d231d777cb814d3a6695d67553748beda5491ce12e529ec2dca32ea7`
- **Adoption Boundary:** Adopt the confirmed workbench information
  architecture, interactions, diagnostic states, and visual direction below.
  Do not copy prototype implementation into application code.

Archive-member locations below use the form
`docs/ui/kb_ui.zip!/Knowledge Engine Lite.dc.html:<line>`.

## Adopted UI Items

### UI-001: Workbench Shell And Responsive Navigation

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-001, REQ-017; DES-001, DES-016
- **Exact Location:** Application shell at archive entry lines 50-120; primary
  route definition near line 2584
- **Reference Context:** Simplified Chinese, populated local workspace; declared
  desktop viewport 1440 x 900 and observed narrow viewport around 644 px; the
  prototype-control bar is excluded
- **Stable Visual Scope:** 220 px desktop navigation, compact sticky context
  bar, breadcrumbs, workspace context, runtime/capability state, active Run
  count, eight primary destinations, and drawer navigation below 900 px
- **Allowed Deviations:** Production component structure and exact pixel values
  may change for accessibility and content fit; locale switching is not adopted
- **Adoption Status:** Confirmed

The runtime indicator must distinguish locally available core services from
optional external capabilities. It must not claim that the complete system is
offline when a selected Profile calls an external provider.

### UI-002: Work Overview And Operational Triage

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-007, REQ-014, REQ-017; DES-008, DES-015, DES-016
- **Exact Location:** `isOv` route at archive entry line 121
- **Reference Context:** Populated, first-use, dependency-unavailable, and
  recoverable-refresh-error states
- **Stable Visual Scope:** Compact command bar, dependency and Plugin-runner
  status band, one dense recent-Run table, failed-Run triage, and recent
  comparison summaries
- **Allowed Deviations:** Counts, columns, pagination, and summary density may
  follow actual API contracts and viewport constraints
- **Adoption Status:** Confirmed

Overview commands route to document submission, Profile creation, Query Lab,
and evaluation execution. Failures expose inspection and contract-permitted
recovery actions rather than generic error-only notices.

### UI-003: Document Submission, Preflight, And Profile Resolution

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-004, REQ-008, REQ-017; DES-007, DES-016
- **Exact Location:** `isDocs` route at archive entry line 265; `upOpen` dialog
  at line 1312
- **Reference Context:** Representative native, scanned, table-heavy,
  presentation, spreadsheet, and long-hierarchical document classes
- **Stable Visual Scope:** Dense document list, synthetic/local file picker,
  preflight facts, explicit Profile selection or automatic matching, matched
  rules, and selected-Profile rationale
- **Allowed Deviations:** Exact preflight fields and supported formats follow
  implemented detectors; external-provider disclosure replaces absolute
  no-upload wording
- **Adoption Status:** Confirmed

Starting ingestion opens the new Ingestion Run. Automatic selection must show
the deterministic inputs and rules that produced the result.

### UI-004: Ingestion Run Inspection And Recovery

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-007, REQ-017; DES-002, DES-004, DES-007, DES-008
- **Exact Location:** `isIng` route at archive entry line 332
- **Reference Context:** SUCCEEDED, RUNNING, FAILED, SKIPPED_BY_CONDITION,
  FALLBACK_SELECTED, CANCELLED, and RETRYING stage states
- **Stable Visual Scope:** Stable typed-stage flow, selected-stage inspector,
  resolved-plan identity and digest, routing decisions, Artifact references,
  timing, metrics, quality signals, attempt, and structured error
- **Allowed Deviations:** Horizontal or vertical stage orientation may follow
  available width; only actions supported by the Run contract are enabled
- **Adoption Status:** Confirmed

Retry preserves the pinned plan. A changed Profile, Plugin, or candidate creates
a new Run rather than mutating the existing experiment.

### UI-005: Artifact Inspector And Source Synchronization

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-006, REQ-007, REQ-017; DES-004, DES-005, DES-008,
  DES-011
- **Exact Location:** `artOpen` drawer at archive entry line 1451
- **Reference Context:** Large responsive drawer opened from Runs, stages,
  Evidence, or citations
- **Stable Visual Scope:** Applicable tabs for raw preview, Canonical structure,
  structure tree, tables, Chunks, Metadata, and Lineage; synchronized source
  locator highlighting; typed Artifact identity and producing lineage
- **Allowed Deviations:** Tabs are conditional on Artifact schema; actual PDF,
  slide, sheet, and document renderers replace the synthetic preview
- **Adoption Status:** Confirmed

The inspector preserves exact source and lineage identifiers without presenting
them as a publication or user-facing version timeline. Raw vector arrays remain
hidden.

### UI-006: Declarative Profile Studio

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-002, REQ-003, REQ-004, REQ-009, REQ-017; DES-002,
  DES-003, DES-006, DES-007, DES-009
- **Exact Location:** `isStudio` route at archive entry line 465
- **Reference Context:** Ingestion and Query Profile tabs; valid, invalid, and
  draft configurations; form and declarative YAML modes
- **Stable Visual Scope:** Searchable Profile list, ordered typed stages,
  compatible Plugin selector, schema-generated parameters, typed ports,
  restricted conditions, timeout, explicit fallbacks, validation results, and
  compiled-plan preview
- **Allowed Deviations:** The exact editor library and drag/reorder mechanism may
  change; accessible move controls must remain available
- **Adoption Status:** Confirmed

Profiles remain declarative. The editor never accepts shell commands, script
paths, executable code, or unrestricted workflow nodes. Working configuration
and candidate duplication do not create approval, publication, rollback, or
user-facing version-management behavior.

### UI-007: Plugin Registry And Contract Detail

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-003, REQ-005, REQ-016, REQ-017; DES-003, DES-016
- **Exact Location:** `isRegistry` route at archive entry line 660; `plugOpen`
  drawer at line 1393
- **Reference Context:** Searchable and filterable registry with available,
  degraded, and unavailable capabilities
- **Stable Visual Scope:** Plugin ID, kind, runner type, accepted and output
  schemas, capabilities, local readiness, implementation digest, contract-test
  result, configuration schema, resource hints, timeout, safe example, and
  recent Runs
- **Allowed Deviations:** Initial kinds and registry rows are limited to actually
  implemented descriptors
- **Adoption Status:** Confirmed

The Registry is inspectable allowlisted configuration. It is not a package
installer, script editor, credential form, or arbitrary container-command UI.

### UI-008: Query Lab, Evidence, And Final States

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-009, REQ-010, REQ-011, REQ-017; DES-009, DES-010,
  DES-011, DES-012, DES-016
- **Exact Location:** `isQuery` route at archive entry line 778
- **Reference Context:** High-precision fact, table-cell, hierarchical
  multi-evidence, ambiguous, unanswerable, verification-failed, repairing, and
  failed scenarios
- **Stable Visual Scope:** Question and Profile controls, indexed Artifact
  selection, resolved plan and stage timing, per-retriever candidates, fusion,
  rerank and context decisions, final answer, citation keys, Evidence items,
  inclusion/exclusion rationale, and synchronized source preview
- **Allowed Deviations:** Visible stages follow the resolved plan; actual scores,
  thresholds, provider names, and timing come from bounded traces
- **Adoption Status:** Confirmed

Product final states use the authoritative contract names `ANSWERED`,
`CLARIFICATION_REQUIRED`, `ABSTAINED`, or `FAILED`; bounded repair and
verification state remain trace detail. Generation-provider readiness and
external-call boundaries must be visible when relevant.

### UI-009: Evaluation Dataset And Reviewed Cases

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-012, REQ-015, REQ-017; DES-013, DES-014
- **Exact Location:** `isEvalset` route at archive entry line 983
- **Reference Context:** Document annotations and query cases; reviewed, draft,
  invalid, incomplete, and first-use states
- **Stable Visual Scope:** Dense list/detail editing, document and question
  annotations, expected and forbidden facts, relevant Evidence, required
  citations, answerability, deterministic answers, slice labels, validation,
  filtering, and explicit review action
- **Allowed Deviations:** Editors and label controls follow the eventual dataset
  schema; generated candidates remain visibly unreviewed
- **Adoption Status:** Confirmed

### UI-010: Evaluation Run And Layered Metrics

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-013, REQ-014, REQ-015, REQ-017; DES-013, DES-014,
  DES-015, DES-016
- **Exact Location:** `isEvalrun` route at archive entry line 1075
- **Reference Context:** RUNNING, COMPLETED_WITH_FAILURES, PASSED_GATES,
  FAILED_GATES, INVALID_DATASET, and JUDGE_UNCALIBRATED states
- **Stable Visual Scope:** Pinned run manifest, separate metric bands by owner
  layer, slice and metric filters, gates, explicit `NOT_APPLICABLE` and
  `INSUFFICIENT_LABELS`, and drilldown from failed aggregate to case evidence
- **Allowed Deviations:** Metric availability and chart form follow labels,
  sample size, and actual metric contracts; no synthetic threshold is binding
- **Adoption Status:** Confirmed

There is no overall quality score. Judge-derived metrics cannot close hard
gates when calibration is missing or invalid.

### UI-011: Reproducible Profile Comparison

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-014, REQ-015, REQ-017; DES-015
- **Exact Location:** `isCompare` route at archive entry line 1202
- **Reference Context:** Baseline and candidate Runs over one pinned dataset;
  single-axis and explicitly non-causal multi-axis examples
- **Stable Visual Scope:** Manifest identity, baseline/candidate metrics,
  absolute and relative deltas, sample/confidence context where meaningful,
  gates, slices, failed cases, latency, and resources shown independently
- **Allowed Deviations:** Chart and table layout may adapt to metric count and
  viewport; the UI may recommend but never activate a Profile automatically
- **Adoption Status:** Confirmed

### UI-012: Unified Run History And Cross-Run Diagnosis

- **Classification:** Adopted Behavior and Visual Reference
- **Applies To:** REQ-007, REQ-014, REQ-017; DES-008, DES-015
- **Exact Location:** `isRuns` route at archive entry line 717
- **Reference Context:** Mixed ingestion, query, evaluation, comparison, and
  contract-test Runs
- **Stable Visual Scope:** Dense filterable table, persistent filters and row
  selection, Run type and status, pinned Profile or Plugin identity, input,
  timing, Trace access, and contract-permitted recovery
- **Allowed Deviations:** Columns and filter values follow implemented Run
  schemas; unsupported recovery controls are omitted
- **Adoption Status:** Confirmed

### UI-013: Shared Visual Language And Interaction States

- **Classification:** Visual Reference
- **Applies To:** REQ-017; DES-001
- **Exact Location:** Design-system `readme.md`, `styles.css`, and
  `_ds_manifest.json` within the prototype archive; route surfaces at archive
  entry lines 121-1311
- **Reference Context:** Light theme; desktop 1440 x 900; responsive breakpoint
  below 900 px; Simplified Chinese; populated and exceptional states
- **Stable Visual Scope:** Compact Archivo typography, neutral work surface,
  flat architectural layout, zero-radius controls, strong section rules,
  restrained red primary-action accent, teal healthy state, blue running/info,
  amber warning/fallback, red failure, Lucide-style icons, visible hover,
  pressed, disabled, and focus states
- **Allowed Deviations:** Token names, implementation framework, exact spacing,
  and pixel values may change. Accessibility, localization-safe sizing, and
  responsive content fit take precedence over pixel matching. Functional
  document previews use real local renderers rather than decorative imagery.
- **Adoption Status:** Confirmed

Use dense tables, split panes, inspectors, tabs, drawers, toolbars, and dialogs.
Do not turn major page sections into floating cards or add decorative gradients,
orbs, glass effects, or oversized marketing typography.

## Demo-only Or Not Adopted

- The top `Prototype control` bar, scenario switches, and prototype-only state
  forcing are not product UI.
- All document names, workspace names, dataset revisions, Runs, timestamps,
  metrics, thresholds, scores, digests, Plugin IDs, model IDs, runner counts,
  error messages, and preview contents are synthetic demo data unless an
  independent Story contract adopts an equivalent fixture.
- `generator.local-instruct@1`, `local · offline`, and the local-runtime summary
  containing `offline` are not adopted provider/runtime facts. The initial
  generation provider is an explicitly configured external DeepSeek API under
  DES-016.
- The upload-dialog claims `不上传到任何远端` and `nothing leaves this machine`
  are not adopted. Product copy must distinguish local document persistence
  from data sent by a selected externally backed stage and disclose that stage's
  boundary before execution.
- The locale selector and English translation are not adopted for Lite. The
  adopted product locale is Simplified Chinese while established engineering
  nouns may remain in English.
- The HTML, inline styles, `support.js`, design-system bundle, in-memory state,
  hand-authored SVG paths, and other generated prototype implementation are
  reference material only and must not be copied into application code.
- Prototype shorthand such as `CLARIFICATION` does not replace the authoritative
  `CLARIFICATION_REQUIRED` final-state contract.

## Open UI Questions

None. Exact framework, component library, renderer choices, and API-bound field
availability belong to just-in-time Story design and must preserve the adopted
behavior and visual scope above.

## Change History

- **2026-09-11:** Created UI Reference v1 from the Claude Design prototype and
  recorded the user-confirmed adoption boundary. Excluded prototype controls,
  demo data, locale switching, generated implementation, and stale fully
  offline wording; aligned provider disclosure with external DeepSeek.
