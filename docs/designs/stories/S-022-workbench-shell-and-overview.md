# Story Design: S-022 - Workbench Shell And Runtime Overview

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-022`, confirmed 2026-09-11.
- Sources checked: the confirmed Story; `REQ-017`; `DES-001` and `DES-016`;
  the FEAT-005 routing manifest; UI-001, UI-002, and UI-013; the exact shell,
  overview, and route-definition regions in the adopted archive; and delivered
  S-001, S-002, S-003, and S-021 code/contracts/tests.
- Material decisions requiring approval: None. `story-pipeline` authorizes the
  implementation choices below. The workbench is Simplified Chinese only and
  has no prototype controls, state-forcing data, or locale selector.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Serve one browser shell with exactly eight semantic navigation links, stable route paths, breadcrumbs, and a URL-derived workspace context. Route components own presentation/loading state only; all runtime facts come from the control API. | Browser keyboard test tabs through all destinations, activates each with Enter/Space, asserts `aria-current`, URL/breadcrumb context persistence, and no duplicate request-derived engine data store. |
| 2 | Add a bounded read-only overview projection that combines non-probing core health, optional capability state, registered Plugin availability, and active Run count. Render core health, optional providers, and Plugins in separate labelled status groups with safe code-based diagnostics and recheck/navigation actions. | API contract tests prove core readiness makes no external call, optional states remain separate, unsafe text cannot appear, and unavailable/degraded/not-configured states produce the correct accessible actions. Component tests cover labels and retry state. |
| 3 | Read recent runs and comparison Artifacts from S-002/S-021 persistence through a new overview query service; expose four commands as navigation only. Render recent Runs, failure inspection/retry only when the Run contract permits it, and actual comparison summaries. | Repository/query-service fixtures cover mixed engine kinds, active/failed/terminal runs, no comparison records, and bounded comparison parsing. UI tests cover populated table, failed-run triage, command routing, and no fabricated counts/values. |
| 4 | Keep a fixed shell and stable overview regions while each API section has loading, empty, dependency-unavailable, and recoverable refresh-error presentation. Preserve the last valid overview during refresh failure and expose retry without hiding primary commands. | Component/browser matrix asserts every state has a distinct accessible heading/status, retry transitions correctly, command placement is stable, and no synthetic default rows or shifting shell geometry occurs. |
| 5 | Use CSS grid/flex with a fixed 220 px desktop navigation at widths at least 900 px and an off-canvas modal drawer below 900 px. Drawer focus is trapped while open, Escape/overlay close it, and body/content never sit beneath it. | Playwright screenshots at 1440 x 900 and 644 px for open/closed navigation, plus DOM scroll-width/overlap checks and keyboard focus-return assertions. |
| 6 | Define local CSS tokens and reusable controls for UI-013: neutral ruled surfaces, square controls, compact density, red command accent, teal/blue/amber/red semantic states, icons, and visible hover/focus/disabled states. | Screenshot assertions for populated, empty, dependency, and refresh-error desktop states and narrow drawer state; automated focus/contrast/overflow checks. |

## Current Code Findings

- `src/kb2_runtime/api.py` currently exposes only the S-001 health endpoints;
  there is no browser application, static asset serving, overview API, or
  client build toolchain. Python/FastAPI is the only current web dependency.
- `HealthService.report(..., probe_external=False)` already provides the
  required core/optional distinction. `/health/ready` deliberately does not
  probe DeepSeek, while `/health/capabilities` only probes it when explicitly
  required. The overview must use the non-probing path on load and refresh.
- S-002 persists authoritative Runs, stages, safe errors, Artifact manifests,
  timestamps, and plan digests in PostgreSQL. It can read one `RunTrace`, but
  has no bounded chronological run-list query suitable for a workbench.
- S-003's `bootstrap_registry()` and `PluginRegistry.inspect()` provide the
  repository-owned allowlist and `runnable`/safe reason view. They must be
  projected from actual capability/runner readiness, not copied into browser
  fixtures.
- S-021 persists immutable `evaluation.comparison/v1` Artifacts and associated
  Evaluation Runs. Those Artifact contents are the source for comparison
  summaries; there is no API/list projection yet.

## Proposed Approach

### Thin Delivery Shape

Add a dependency-free static application served by FastAPI under `/workbench/`
and a single versioned read-only API at `GET /api/workbench/overview`. Use
standard ES modules, CSS, and browser History API routing rather than adding a
Node build chain or a second server. FastAPI owns bootstrap HTML and static
asset caching; the browser owns only current route, drawer visibility, focus,
and fetch state. It does not compile Profiles, invoke Plugins, calculate
metrics, infer recovery eligibility, or retain a browser-side engine model.

The shell's eight destinations and paths are fixed for this Story:

| Destination | Path | S-022 behavior |
|---|---|---|
| Overview | `/workbench/overview` | Implemented overview. |
| Documents | `/workbench/documents` | Shell route placeholder for S-024. |
| Profile Studio | `/workbench/studio` | Shell route placeholder for S-023. |
| Query Lab | `/workbench/query` | Shell route placeholder for S-025. |
| Evaluation Dataset | `/workbench/evaluation-dataset` | Shell route placeholder for S-026. |
| Compare | `/workbench/compare` | Shell route placeholder for S-027. |
| Runs | `/workbench/runs` | Shell route placeholder for S-027. |
| Plugin Registry | `/workbench/plugins` | Shell route placeholder for S-023. |

Placeholder routes state that their workflow is not yet available; they do not
invent controls, data, or destination-specific state. The URL query parameter
`workspace` is optional, bounded, and presentation-only. Its selected value
is preserved through navigation and appears in breadcrumb/context copy, but
does not select database data or imply tenancy. When absent, display the local
runtime context rather than a synthetic workspace name.

### Overview API And Read Model

Create frozen, extra-forbidden Pydantic models in a focused `workbench`
package. The response has `contractVersion: "workbench-overview/v1"` and
contains only bounded safe fields:

```text
core: { status, checkedAt, components[] }
optionalCapabilities: [{ id, status, code, provider?, model?, latencyMs }]
plugins: [{ pluginId, runnable, reason? }]
activeRunCount: non-negative integer
recentRuns: [{ id, engineKind, state, terminalState?, createdAt, startedAt?, endedAt?,
              planDigest, failure?: { code, retryable } }]
recentComparisons: [{ artifactId, runId, createdAt, mode, axis?, recommendation }]
```

`WorkbenchOverviewService` performs one bounded request (maximum eight recent
Runs, four comparisons) through read-only repository methods. The run-list SQL
orders by `created_at DESC, id DESC`, derives active count from `PENDING` and
`RUNNING`, and returns only engine kind, lifecycle/timing, plan digest, and
the latest safe failed-stage code/retryability. It does not return stage
summaries, Artifact locators, source text, provider bodies, credentials, or
raw configuration. A comparison query selects successful
`evaluation.comparison/v1` Artifacts in newest order, verifies its safe
canonical content against the manifest digest before extracting only mode,
axis, and recommendation, and skips malformed/ineligible records rather than
publishing partial invented values.

For every overview request, call `HealthService.report(probe_external=False)`
once. Components populate `core`; capabilities populate
`optionalCapabilities`, never an aggregate "offline" label. Build the Plugin
projection with the shared registry and readiness functions based on this
same health snapshot. A non-ready container runner or declared capability
makes the relevant Plugin non-runnable without converting a healthy core into
a failed core. The endpoint returns a safe 503 problem projection only when
the overview dependencies themselves cannot be read; the client continues to
show its last successful snapshot and offers a refresh. It never asks the
browser to call provider health endpoints directly.

The four commands only navigate: document submission to Documents, Profile
creation to Studio, Query Lab to Query, and evaluation execution to Evaluation
Dataset. A failed Run "inspect" action routes to Runs with its opaque `runId`.
Retry is rendered only when API `failure.retryable` is true, and S-022 routes
it to the destination inspection context because no generic retry command is
in the S-002 Run API. It must not issue an invented retry request.

### UI And Interaction

Use semantic landmarks (`nav`, `header`, `main`, labelled sections), native
links/buttons, Lucide-style inline icon components, `aria-current="page"`,
and `aria-live` for refresh/loading/result notices. At desktop width the
sidebar is `220px` fixed in the grid and the compact context bar is sticky.
Below 900 px the sidebar is removed from layout and becomes an inert-backed
dialog drawer; it has an accessible name, modal focus loop, Escape/overlay
close, and focus return to the menu button. No locale UI is included.

Overview keeps its title/command row, dependency band, recent-Run section,
failed-Run triage, and comparison section in stable document order. Dense
tables may horizontally scroll within their own region at narrow widths; the
page itself must not horizontally overflow. Loading uses fixed-height table
rows/skeletons. First use shows no records and routes through the actual
document command. Dependency-unavailable shows the health-derived components,
not a fake outage. A refresh error leaves the last snapshot visible; before a
first successful load it presents a bounded error region plus retry.

CSS variables encode the adopted light palette, borders, spacing, compact
Archivo/system fallback typography, and semantic statuses. Controls have zero
corner radius; rules divide sections; the red accent is reserved for primary
commands. Avoid cards, gradients, prototype toolbar, local/offline claims,
or any synthetic values.

## Relevant Impacts

- **API:** Add the overview read model/endpoint and HTML/static routes. Health
  endpoint contracts remain unchanged; API response bodies use safe IDs,
  lifecycle state, code, and bounded aggregates only.
- **Data and migration:** Add read-only repository queries/index-friendly
  ordering over existing `runs`/Artifacts. No database schema, Artifact type,
  Profile, Registry, or Run lifecycle migration is needed.
- **Security:** The UI receives no secret, provider request/response, Artifact
  location/content, arbitrary error text, filesystem path, command, or
  executable configuration. Query params are presentation-only and validated.
- **Observability:** Every overview refresh maps health codes and persisted
  lifecycle fields to visible diagnostics. Client fetch failure is distinct
  from core/capability/Plugin status and is never stored as an engine outcome.
- **Compatibility:** Future S-023 through S-027 replace route placeholders
  while retaining the shell, paths, context semantics, and overview endpoint.

## Alternatives And Risks

- Adding React/Vite was rejected: this repository has no frontend package
  baseline, and a small static shell needs no build/runtime dependency. Native
  modules remain sufficient until a later Story has a demonstrated shared UI
  complexity need.
- Reusing `/health/ready` plus browser assembly was rejected: it cannot supply
  runs/comparisons and would invite duplicated readiness inference. The server
  projection has one explicit safe contract.
- Eagerly probing DeepSeek on each overview refresh was rejected because it
  violates S-001's optional-capability boundary and makes ordinary workbench
  availability dependent on an external provider.
- The initial runtime may have no persisted Runs/comparisons. The empty state
  is intentional and must not be filled with prototype sample values.
- Browser visual tests introduce a browser-runtime dependency. Keep them
  isolated from current Python contract tests, use pinned Playwright tooling in
  the test environment, and make their screenshots deterministic from fixture
  API responses rather than live provider/Docker availability.

## Test Strategy

- Add FastAPI/API contract tests for static entry routing, response schema,
  response bounds/order, safe serialization, no external health probe, core
  versus optional/Plugin separation, unknown/bad query rejection, empty
  persistence, comparison filtering, and dependency failure translation.
- Add repository/service tests with fake health, registry, trace, and Artifact
  adapters for failed/retryable/non-retryable Runs, active count, chronological
  tie-breaking, malformed comparison content, and no duplicate state logic.
- Add browser component/end-to-end coverage using fixture-backed overview API:
  all eight keyboard routes, breadcrumbs/workspace preservation, commands,
  populated/empty/dependency/loading/error states, refresh recovery, semantic
  labels, drawer keyboard operation, and focus return.
- Add deterministic screenshot/overflow checks at 1440 x 900 for populated,
  empty, dependency, and refresh-error states, and at 644 px for drawer
  closed/open. Assert `document.documentElement.scrollWidth <= innerWidth` and
  that drawer/content bounding boxes do not overlap in the closed state.
- Run existing health, trace, and Plugin contract/integration tests unchanged
  to protect the S-001--S-003 boundaries.

## Implementation Checklist

- [ ] Add `kb2_runtime.workbench` contracts, read-only service, and repository
  projections with bounded/sanitized output.
- [ ] Wire FastAPI overview/static routes without changing existing health
  endpoint semantics.
- [ ] Add dependency-free shell modules/styles and all eight route states.
- [ ] Implement overview states, health/capability/Plugin distinction, and
  contract-permitted navigation actions.
- [ ] Add API/service, browser accessibility, responsive/overflow, and visual
  regression coverage; run focused and existing regression suites.

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-022 `story-pipeline` invocation on 2026-09-12; no separate
product decision is required.

## Change History

- **2026-09-12:** Created just-in-time implementation design from confirmed
  S-022 and its exact REQ/DES/UI/Feature anchors and current delivered code.
