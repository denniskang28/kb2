# Story Design: S-024 - Document, Ingestion Run, And Artifact UI

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-024`, confirmed 2026-09-11.
- Sources checked: S-024; UI-003, UI-004, UI-005, and UI-013; delivered
  S-010, S-022, and S-023 code/contracts/tests. `DES-016` and FD-003/FD-004
  were checked only to resolve the selected-stage disclosure and Artifact
  provenance boundaries.
- Material decisions requiring approval: None. The Story Pipeline invocation
  authorizes the bounded workbench API and dependency-free browser UI below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | A raw-body preflight endpoint holds one bounded, short-lived submission token, detects only implemented source facts, compiles the selected saved ingestion Profile, and returns explicit or automatic resolver facts before a Run can start. | API/service tests cover detection, explicit and automatic selection, rule/candidate/rationale output, expiry, malformed input, and no Run before confirm. |
| 2 | The compiled plan is inspected server-side before confirmation. A disclosure lists only selected stages whose registered Plugin has an externally backed capability; local Artifact persistence is described separately and no absolute privacy claim is rendered. | Contract/browser tests cover local-only and external-stage plans, safe disclosure, and disabled submit until acknowledgement. |
| 3 | A safe ingestion Run projection is read from existing `RunTrace` data. It renders the pinned digest, resolution evidence, attempted resolved stages, Artifact references, timing, metrics, quality signals, attempts, and `SafeError`; no inferred or unexecuted stage is fabricated. | Projection tests cover running/succeeded/failed/skipped/fallback/retry records, ordering, redaction, and absent trace. |
| 4 | The server exposes an explicit action-capability projection. Stop is available only for an in-process active submission with a cancellation token; automatic retry is historical trace evidence, not a second arbitrary retry command; rerun returns to preflight and always creates a newly compiled Run. Artifact buttons exist only for eligible persisted references. | Service/API tests assert action eligibility, cancellation ownership, immutable digest preservation, no manual retry endpoint, and a changed Profile producing a new Run. |
| 5 | A schema-gated Artifact inspector verifies stored content through `ArtifactService`, parses only supported Canonical/Chunk schemas, and emits a bounded view model keyed by real element/table/chunk IDs and locators. The client uses those locators for source highlighting and lineage navigation. | Schema/content tests cover Canonical, tables, Chunks, metadata, lineage, corrupt/missing content, unsupported schemas, exact locator synchronization, and no vector array. |
| 6 | Replace Documents and Runs placeholders in the existing shell and add its responsive inspector/dialog behavior. Use compact ruled panes, semantic state colors, keyboard focus return, and scoped scrolling below 900 px. | Fixture-backed browser screenshots/interactions at 1440 x 900 and 644 px, focus/escape checks, source-sync checks, and no horizontal-overflow/overlap assertions. |

## Current Code Findings

- S-022 already serves a dependency-free static workbench shell, routes
  `/workbench/documents` and `/workbench/runs`, and establishes the responsive
  navigation/focus conventions and visual tokens. S-023 supplies durable
  validated ingestion Profile workspaces and server-owned compilation.
- S-010 owns resolution, immutable plan creation, source materialization,
  linear execution, declared fallback, and exactly one automatic retry of a
  retryable failed candidate. `RunTrace` already contains ordered stage
  attempts, inputs, outputs, metrics, quality signals, safe errors, and frozen
  `IngestionEvidence`; `ArtifactService` verifies content digest/location.
- There is no document preflight/submission API, ingestion worker coordinator,
  Run projection, Artifact inspector projection, externally backed-stage
  disclosure, or operator lifecycle-action contract. Run states do not support
  a generic persisted stop/retry transition, so the UI must not invent one.

## Proposed Approach

### Bounded Submission And Execution Boundary

Add `workbench.documents` (or a similarly focused module) with frozen request
and response contracts, an injectable `DocumentWorkbenchService`, and a
process-local `IngestionJobCoordinator`. Use raw request bodies rather than a
new multipart dependency or JSON/base64 source transport:

1. `PUT /api/workbench/documents/preflight` accepts up to the existing 16 MiB
   source limit plus bounded filename/media-type headers and a saved ingestion
   Profile ID. It creates an opaque TTL-limited token in the coordinator.
2. The service derives only deterministic, implemented observables (declared
   media type, normalized extension, byte size, and conservative local
   signatures such as PDF/OOXML containers). It compiles the saved Profile set
   through the S-023/engine compiler, runs the existing resolver, and returns
   detected facts, candidates, evaluated rules, selected Profile, plan digest,
   resolved-stage summary, and disclosure. It never claims support beyond the
   returned source schema/detector facts.
3. `POST /api/workbench/documents/preflights/{token}/runs` accepts either the
   matching automatic selection or an explicit Profile ID plus the required
   disclosure acknowledgement. It consumes the token once, recompiles and
   resolves immediately, then starts the existing ingestion engine using the
   exact source and `ResolutionRequest`. The coordinator returns the real Run
   ID once it is created and retains only a cancellation event/task for its
   active local lifetime.

The coordinator must not persist upload tokens, source paths, browser names,
raw bytes, credentials, provider bodies, or task details into trace metadata.
Expired/consumed/unknown tokens return one safe workbench problem code. A
failed preflight or confirmation creates no Run. The Profile and Registry stay
the owners of declarative values and Plugin selection; this service never
accepts arbitrary Plugin IDs, code, commands, filesystem locations, or
execution configuration.

External disclosure is driven from each selected resolved candidate's
registered capability classification, supplied by the server as a compact
`externalStages` list. Capability-to-external-boundary mapping is server-owned
configuration adjacent to runtime capability definitions, not a browser
Plugin-ID allowlist. It names the selected stage/Plugin/capability and states
that its document content may be sent to that external provider. Empty means
only that no selected stage is externally backed; it does not make a broader
privacy, offline, or residency claim.

### Run And Recovery Projection

Add read methods to `TraceRepository` for a single bounded ingestion
`RunTrace` and eligible Artifact manifests; reuse `RunService.get_run_trace`
and `ArtifactService` for validation. `DocumentWorkbenchService` maps this to
`workbench-ingestion-run/v1` with the plan digest, state/times, resolver
evidence, and stage rows ordered by recorded stage key then attempt number.
Rows include only recorded attempted stages and safe summaries/errors,
Artifact references, metrics, and quality signals. A derived logical status
may label recorded candidate-selection signals as selected, fallback, skipped,
or retry attempt, but it may not change the trace state/result.

Expose:

| Endpoint | Behavior |
|---|---|
| `GET /api/workbench/ingestion-runs/{run_id}` | Safe persisted trace projection plus action capabilities. |
| `POST /api/workbench/ingestion-runs/{run_id}/stop` | Sets the coordinator cancellation event only when that Run is actively owned by this process; otherwise returns `RUN_STOP_UNAVAILABLE`. |
| `GET /api/workbench/artifacts/{artifact_id}` | Safe manifest plus conditional inspector view after digest-verified read. |

There is deliberately no endpoint for a manual stage retry or replaying a
pinned plan with changed configuration. S-010's one automatic retry remains
visible as multiple recorded attempts with the same stage key and plan digest.
The "rerun" command returns to preflight with the source Artifact selected as
an existing immutable input; it must complete fresh resolution/compilation and
create a new Run. A changed Profile/Plugin/candidate therefore cannot mutate
or retry the original plan. Stop is not shown for completed Runs, and is not
shown after a service restart because no local cancellation ownership exists.

### Artifact Inspector And UI

The Artifact endpoint first reads through `ArtifactService` so lineage-eligible
location and digest validation remain authoritative. It returns the common
safe manifest/producer/parent/metric/signal metadata and conditionally parses
only supported schema pairs:

- source/raw: a bounded local preview descriptor; textual preview only when
  the media type is safely renderable, otherwise an explicit unavailable
  preview state, never a synthetic format renderer;
- `canonical.document/v1`: metadata, element/tree/table records, exact stable
  IDs, and discriminated locators;
- `chunk.set/v1`: chunks, parent/child relationships, source element IDs, and
  exact citations/locators;
- all other known Artifact schemas: Metadata and Lineage only, with no raw
  vector/embedding arrays; unknown/corrupt/missing content is a safe unavailable
  inspector state.

The browser renders Documents with a dense list, upload/preflight dialog,
explicit/automatic selector, matched-rule disclosure, plan stages, and a
confirmation command. Runs uses a stable stage flow plus selected-attempt
inspector and only server-enabled Stop/Artifact/Rerun controls. The shared
Artifact drawer has schema-conditional tabs, with no empty fake tabs. Selecting
a Canonical element, table, or Chunk citation updates one source-highlight
state keyed by its returned locator; selection from the source view selects
the same stable ID. The raw preview uses an actual local browser renderer only
for a returned safe preview; it never turns locator data into an invented
document rendering.

Extend the existing native-DOM `workbench.js` and CSS rather than adding a
frontend build system. Preserve the shell's desktop sidebar and narrow drawer.
At less than 900 px, lists/panes stack and the inspector is a labelled modal
drawer with Escape, focus trap, and focus return. Wide tables/JSON scroll only
inside labelled panels. Use Simplified Chinese, zero-radius controls, rules,
and the existing teal/blue/amber/red semantic states; no cards, gradients, or
prototype controls/data.

## Relevant Impacts

- **API/data:** Add bounded preflight, ingestion submission/read/stop, and
  Artifact-inspector endpoint contracts plus read queries over existing Runs,
  attempts, Artifacts, and lineage. Upload tokens/jobs are in-memory and
  ephemeral; no migration, Profile history, lifecycle-governance system, or
  new persistent document table is required.
- **Security:** Content is accepted once within the existing size bound and
  persists only as the existing source Artifact after submission. Client
  projections exclude storage locators, raw provider payloads, credentials,
  paths, commands, arbitrary configuration, unsafe errors, and raw vectors.
  Browser rendering uses text nodes/Blob URLs, never `innerHTML`.
- **Observability:** Resolution evidence, digest, stage attempts, safe failures,
  fallback/automatic retry, metrics, quality, and Artifact lineage are visible
  without duplicating execution decisions. Coordinator failures and expired
  tokens remain distinct workbench problems and are not written as engine
  outcomes.
- **Compatibility:** Existing engine, Profile compiler, Registry, trace
  contracts, shell routes, and overview endpoint retain ownership and behavior.
  `/workbench/documents` and `/workbench/runs` graduate from placeholders;
  `/workbench/artifacts/{id}` is an inspector route/context, not a new Artifact
  persistence model.

## Alternatives And Risks

- Multipart uploads were rejected because the dependency baseline lacks its
  parser and raw-body tokens avoid both a new package and base64 expansion.
- A generic manual retry/cancel lifecycle was rejected: S-010 permits only
  bounded automatic retry and has no durable control-plane lease. Showing it
  would falsely imply mutability of pinned Runs.
- Direct Artifact-store reads in the browser were rejected because they expose
  locators and bypass digest/lineage validation.
- Process-local active jobs cannot survive restart. The action-capability
  contract makes that limitation visible rather than offering an ineffective
  Stop command; completed trace inspection remains durable.

## Test Strategy

- Add unit/service and FastAPI tests for raw-body bounds, detector facts,
  token expiry/single use, explicit/automatic resolution evidence, compile
  failures, source-schema mismatch, disclosure acknowledgement, external vs
  local-only plans, background receipt, and no pre-confirmation Run.
- Cover Run projection for every trace state/attempt pattern, plan identity,
  safe-error redaction, persisted-action eligibility, stop ownership, rerun
  new-Run semantics, and unsupported/missing Runs.
- Add Artifact tests for digest/lineage validation; safe malformed/missing
  content; Canonical/tree/table and Chunk/citation projections; exact
  source-locator mapping; metadata/lineage; and absent embedding vectors.
- Extend the fixture browser server and browser tests for preflight automatic
  match/external disclosure, running, failed/skipped/fallback/retry detail,
  Inspector Canonical/table/Chunk/lineage selection, dialog/drawer keyboard
  behavior, and action visibility. Capture deterministic screenshots at 1440
  x 900 and 644 x 900, asserting page overflow is absent and closed-pane boxes
  do not overlap.
- Run existing ingestion Profile/engine, trace persistence, Artifact,
  workbench, Studio, and browser regression suites. Docker lifecycle evidence
  remains subject to the existing Compose startup limitation.

## Implementation Checklist

- [ ] Add focused workbench contracts/service/coordinator and safe
  repository/read adapters for preflight, submission, run, action, and
  Artifact projections.
- [ ] Wire FastAPI raw-body, confirmation, Run/action, and Artifact routes;
  compose the existing ingestion engine without reimplementing resolution or
  execution.
- [ ] Implement server-owned external-stage classification/disclosure and
  conditional Artifact view parsing.
- [ ] Replace Documents/Runs placeholders and add Artifact inspector/source
  synchronization in the established static shell/CSS.
- [ ] Add service/API/browser/accessibility/visual tests and run focused plus
  existing regression coverage.

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-024 `story-pipeline` invocation on 2026-09-13; no separate
product decision is required.

## Change History

- **2026-09-13:** Created just-in-time design from confirmed S-024, exact
  adopted UI anchors, and delivered engine/workbench contracts.
