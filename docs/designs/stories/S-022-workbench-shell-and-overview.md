# Story Design: S-022 - Workbench Shell And Runtime Overview

## Status

Approved for Story Pipeline repair development.

## Story Contract Snapshot

- Story: `S-022`, confirmed 2026-09-11 and currently implemented.
- Repair trigger: confirmed UI-001, UI-002, and UI-013 behavior and visual
  direction are materially under-rendered by the current browser client. This
  is an implementation correction, not a product, Feature, or UI Reference
  change.
- Sources checked: the self-contained Story; exact shell and route regions at
  archive entry lines 50-120 and 2584-2594; exact Overview region at lines
  121-263; confirmed UI-001, UI-002, and UI-013 entries; design-system
  `readme.md`, `styles.css`, and manifest; current Overview contracts/service;
  current static shell/CSS; and Chrome/CDP browser tests.
- Material decisions requiring approval: None. The invoking repair pipeline
  authorizes the choices below. No prototype implementation or demo fact
  becomes production code or data.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Separate eight `PRIMARY_DESTINATIONS` from deep-route metadata. Keep `/workbench/evaluation-run` as a child of Evaluation Dataset, but remove it from primary sidebar/drawer navigation. Build both nav instances from one descriptor list, preserve validated `workspace` in every route, and mark the parent destination current for child routes. | CDP asserts exactly eight primary links in desktop and drawer nav, unique expected paths, `aria-current`, child-route parent selection, workspace propagation, keyboard activation, and focus order. |
| 2 | Load the existing `workbench-overview/v1` projection once per page through a shared snapshot controller and render four independently labelled shell groups: core, optional external capability, Plugin runnable count, and active Runs. Render complete core/capability/Plugin detail again in the Overview dependency band using only server-owned statuses and safe codes. | Fixtures independently vary core, optional capability, and Plugin readiness. DOM assertions prove no aggregate offline claim, no external probing, safe labels/codes, stale/error distinction, and correct Registry/refresh actions. |
| 3 | Replace the one-line Overview with the adopted command row, dependency band, dense recent-Run table, failed-Run queue, and recent-comparison list. Consume every relevant existing API field; commands remain navigation, and recovery links lead to owner-authoritative Run diagnosis rather than issuing a generic retry. | Populated fixture asserts four commands/routes, all Runs, durations/statuses/digests, failure code and retryability-dependent recovery link, comparison summaries, and no synthetic profile/input/metric values. |
| 4 | Give shell context and each Overview region explicit loading, first-use empty, dependency-unavailable, and recoverable refresh-error renderers with fixed structural slots. A failed refresh preserves and marks the last successful snapshot stale; a first-load failure retains commands and section geometry with bounded error copy. | Deterministic fixture sequences cover loading-to-success, empty, independent dependency loss, first-load error, and success-then-refresh-error. CDP checks `aria-live`/`role`, stale retention, retry recovery, disabled state, and stable section bounds. |
| 5 | Rebuild shell geometry around a sticky 220 px desktop sidebar and compact sticky context bar. Below 900 px, remove the sidebar from layout and expose a modal 220 px drawer with backdrop, inert background, focus loop, Escape/backdrop/link close, and focus return. | Geometry assertions and screenshots at 1440 x 900 and 644 x 900 prove sidebar width, menu visibility, drawer open/closed bounds, no overlap, no page horizontal overflow, and focus restoration. |
| 6 | Establish local UI-013 tokens plus S-022-only reusable primitives for icons, command links, status tags, section headers, dense tables, notices, empty states, and skeleton rows. Use self-hosted Archivo, a documented Lucide subset, zero radius, strong rules, restrained red commands, and teal/blue/amber/red state roles with complete hover/active/focus/disabled styling. | Token/component checks plus accepted golden-image comparison for desktop Overview states and narrow shell/drawer states; CDP also checks computed radius, focus outline, stable sizes, and absence of prototype controls/locale UI. |

## Current Code Findings

- `workbench.js` uses one route array for dispatch and primary navigation. It
  contains nine entries because `evaluation-run` was added as a primary
  destination, while UI-001 and S-022 require eight. The evaluation route is
  valid S-026 behavior and must remain reachable as a child route.
- `shell()` renders the brand, duplicated links, one breadcrumb, and a text
  hamburger. It does not render workspace, core, optional capability, Plugin,
  or active-Run context.
- `overview()` fetches the correct endpoint but collapses the entire projection
  to `coreStatus` and `activeRunCount`. Recent Runs, failures, comparisons,
  dependency details, commands, empty state, and refresh recovery are absent.
- `workbench-overview/v1` already exposes the bounded safe fields required for
  the repair: checked time; core aggregate/components; optional capabilities;
  Plugin runnable state/reason; active count; eight Runs; and four verified
  comparison summaries. No API, repository, database, or migration change is
  required.
- The CSS has the 220 px grid and zero radius, but uses Arial, a small token
  set, no shared semantic status primitives, incomplete interaction states,
  and little of UI-002's ruled composition. The same assets serve S-023 through
  S-027, so repair selectors must be scoped and legacy token aliases retained.
- The S-022 browser matrix directly launches Chrome with a fixed port/delay and
  only checks that a PNG larger than 1 KB exists. It neither compares with a
  reference nor waits for explicit UI state. The current run gives two passing
  cases and a loading/644 px capture/termination failure; this is not visual
  parity evidence.

## Proposed Approach

### Route And Shell Model

Use this immutable primary descriptor set:

| Destination | Path | Icon | Child route handling |
|---|---|---|---|
| Overview | `/workbench/overview` | grid | None |
| Documents | `/workbench/documents` | file-text | Ingestion diagnosis remains in Runs |
| Profile Studio | `/workbench/studio` | sliders-horizontal | None |
| Query Lab | `/workbench/query` | search | None |
| Evaluation Dataset | `/workbench/evaluation-dataset` | list-checks | `/workbench/evaluation-run` selects this parent |
| Compare | `/workbench/compare` | git-compare | None |
| Runs | `/workbench/runs` | layers | Run-detail query context remains here |
| Plugin Registry | `/workbench/plugins` | plug | None |

Keep `ROUTE_META` separate so dispatch and breadcrumbs can describe
`evaluation-run` without adding a ninth primary link. Continue the strict
workspace validator. Workspace is presentation context only: show the
validated value as plain context, show `本地运行时` when absent, and never offer
prototype workspace demo choices or infer tenancy.

`shell(content)` becomes a stable three-part structure: primary sidebar,
compact context header, and route content. Sidebar and drawer consume the same
nav builder. On narrow screens the drawer owns a labelled close icon, modal
focus loop, inert shell background, backdrop click, Escape/link close, and
focus return. It never contains prototype runtime/demo footer facts.

Create one page-local `OverviewSnapshotController` around
`GET /api/workbench/overview`. It may cache the last successful response and
fetch promise for presentation consistency only; it does not persist or derive
engine state. Shell context and Overview subscribe to the same controller, so
the Overview route does not make duplicate requests. Other routes request the
projection once to populate shell context. Refresh starts one new request and
updates both subscribers.

The context bar presents compact, separately labelled facts:

- `核心` uses server-owned `coreStatus` directly;
- `外部能力` summarizes returned capability statuses and exposes every safe
  status/code in accessible detail;
- `Plugin` reports runnable/total from the returned boolean projection without
  claiming that core is unavailable;
- `活动 Run` displays `activeRunCount` and links to Runs.

Count formatting and semantic colors are presentation only. They never change
command eligibility or manufacture a global readiness state. During load each
group holds a fixed-width skeleton. On first failure each says `状态不可用`;
after refresh failure the last values remain with `数据可能已过期`.

### Overview Composition And State

Keep the archive's stable document order without copying its markup:

1. A ruled title/command row with four links: `提交文档`, `新建 Profile`,
   `打开 Query Lab`, and `运行评估`, targeting Documents, Studio, Query Lab,
   and Evaluation Dataset while preserving workspace.
2. A dependency band grouped as core components, optional capabilities, and
   Plugins. Each shows identifier, localized status, and safe code/reason.
   Unavailable items add one notice with `重新检查` and `打开插件注册表`;
   optional `not_configured` remains distinct from core outage.
3. A ruled split with recent Runs on the wider side and failure/comparison
   sections on the narrower side at desktop width. Narrow layouts stack; only
   the table wrapper may scroll horizontally.

The Run table renders only API-owned facts: shortened ID with full UUID in
accessible text/title, engine kind, shortened plan digest, lifecycle state,
elapsed duration when both endpoints exist, and created time. Each row has an
explicit Runs inspection link rather than a clickable pseudo-row. Missing
timestamps display a neutral placeholder and never become zero duration.

The failure queue filters the returned recent Runs. It shows Run identity,
engine kind, safe failure code, inspection, and a recovery navigation link only
when `failure.retryable` is true. The link opens owner-authoritative Run
diagnosis; it does not call retry. Comparison rows show mode, optional axis,
recommendation, and time and route to Compare without inventing selection.

Loading uses fixed-height skeleton rows. With no Runs/comparisons, each section
owns a concise first-use empty state; the Run state repeats the real document
command. Dependency unavailability does not replace persisted activity. A
first fetch error keeps commands and stable section frames, adds a bounded
alert/retry, and labels context unavailable. A later refresh error preserves
data, labels it stale, and offers retry. Success clears the stale state without
reconstructing the shell.

### Visual Tokens And Reusable Primitives

Expand `workbench.css` with UI-013 variables for ground/surface, ink, neutral
and accent ramps, 4/8/12/16/24/32 px spacing, zero radii, rule weights, compact
type, and healthy/running/warning/failure roles. Retain `--ink`, `--muted`,
`--rule`, `--panel`, `--accent`, `--blue`, `--teal`, and `--red` as aliases so
later Story screens do not change accidentally.

Self-host Archivo 400/600/800 Latin files rather than depending on the
prototype's Google Fonts import or a workstation. Include the upstream license
and pinned source/checksum. Simplified Chinese uses a declared system CJK
fallback. Vendor only required Lucide icon definitions from one pinned release
with its license; do not copy prototype paths or hand-draw replacements.

Add native-DOM factories for `icon`, `iconButton`, `commandLink`, `statusTag`,
`sectionHeader`, `notice`, `emptyState`, `skeletonRows`, and `denseTable`. They
return semantic native elements and contain no engine decisions. Use them for
S-022 only. Existing S-023 through S-027 renderers retain behavior/selectors;
page-specific conversion belongs to their repairs.

Every S-022 interactive class defines hover, active, focus-visible, and
disabled states. Focus is a 2 px red outline; semantic color is paired with
text/icon. Controls/tags have stable height and zero radius. Major sections are
unframed ruled regions, not cards; add no gradients, shadows, decorative
imagery, toolbar, locale selector, or offline claim.

## Relevant Impacts

- **UI modules:** Update `static/workbench.js` for route separation, shared
  snapshot state, shell, drawer, and Overview. Add small
  `static/workbench-ui.js` and pinned icon module only if needed to keep native
  DOM factories independently testable; no framework/build chain is added.
- **Styles/assets:** Retune `static/workbench.css` with compatible aliases and
  scoped Shell/Overview primitives. Add locally served pinned Archivo/Lucide
  assets and license notices. `artifact.css` and other page compositions remain
  unchanged.
- **API/data:** Keep `workbench-overview/v1`, persistence queries, and routes
  unchanged. Add no migration, Artifact, or client-owned domain state.
- **Security:** Continue text-only DOM construction and strict workspace/UUID
  routing. Display only bounded identifiers, enums, and safe codes. Add no raw
  errors, Artifact content, credentials, paths, commands, or prototype data.
- **Compatibility:** Preserve every URL and downstream dispatch.
  `evaluation-run` remains addressable and selects Evaluation Dataset in
  primary navigation. Later Story browser scenarios are required regressions.

## Deterministic Visual Comparison Evidence

Keep the FastAPI fixture app and Chrome/CDP helpers, but replace the S-022
direct `--screenshot` loop with a CDP-controlled scenario runner:

1. Allocate server/debug ports with `_free_local_port()` and launch/close via
   `_launch_isolated_chrome()` and `_close_isolated_chrome()` so failure cannot
   strand Chrome.
2. Add test-only deterministic fixture controls for `populated`, `empty`,
   `dependency`, `first-error`, and request sequences. Loading uses a release
   endpoint/event instead of sleep; refresh-error uses one success followed by
   controlled 503. Production never sees these controls.
3. Wait through CDP for explicit `data-overview-state` and `document.fonts.ready`
   rather than delay. Set exactly 1440 x 900 or 644 x 900 at DPR 1; disable
   animations, transitions, and caret; keep fixture values deterministic.
4. Commit accepted PNGs under `tests/visual/baselines/s022/` with a manifest
   recording viewport, scenario, UI anchor, prototype SHA, fixture revision,
   exclusions, and baseline SHA. Generate them from production plus fixtures
   only after side-by-side review against exact adopted prototype regions; do
   not import prototype markup, styles, or demo facts.
5. Use Chrome as the PNG decoder: load baseline/current into canvas through
   CDP, compare RGBA, and return differing-pixel ratio/bounds. On failure write
   baseline/current/high-contrast-diff PNGs to pytest artifacts. This adds no
   platform imaging tool or Python image dependency.
6. Gate stable regions at no more than 0.5% differing pixels with per-channel
   tolerance 12. Separately assert geometry within 1 px for sidebar, context
   bar, main boundaries, drawer, and scoped overflow. Do not mask text/status
   regions because fixtures and local fonts are deterministic. Never update a
   baseline automatically.

Required golden scenarios:

| Viewport | Scenario | Evidence |
|---|---|---|
| 1440 x 900 | Populated | Complete shell/context, commands, dependencies, Run table, failure queue, comparisons |
| 1440 x 900 | Empty | Stable commands and first-use Run/comparison states |
| 1440 x 900 | Dependency unavailable | Independent core/capability/Plugin states and actionable notice |
| 1440 x 900 | Loading | Fixed skeleton geometry before controlled release |
| 1440 x 900 | Refresh error after success | Last snapshot retained and visibly stale with retry |
| 644 x 900 | Populated, drawer closed | Menu replaces sidebar, stacked Overview, no page overflow |
| 644 x 900 | Populated, drawer open | 220 px modal drawer/backdrop with coherent bounds |

First-load error and retry-to-success require semantic/geometry assertions even
though refresh-error is the primary error golden. Every image check is paired
with DOM assertions; screenshot existence is never sufficient.

## Alternatives And Risks

- React/Vite remains unjustified for a native-DOM repair. Small factories and
  scoped classes provide reuse without a second build/runtime.
- Copying prototype HTML/CSS would violate UI governance and carry demo facts
  and network imports. Implement independently from adopted evidence.
- A single aggregate readiness badge was rejected because it conceals
  core/optional/Plugin distinction. Presentation counts remain independently
  labelled and never govern engine behavior.
- Pixel-only comparison can approve semantic breakage; DOM-only tests miss
  visual drift. Require controlled pixel and semantic/geometry evidence.
- Shared CSS can regress later pages. Preserve token aliases, scope new classes,
  and run representative Studio, Documents, Query, Evaluation, Compare, Runs,
  Registry, and Artifact inspector scenarios at both viewports.
- Rasterization updates can add antialiasing noise. Self-hosted fonts, DPR 1,
  channel tolerance, and bounded pixel ratio absorb noise without masking
  layout/component changes.

## Test Strategy

- Keep current Overview service/API tests to prove the bounded server contract;
  add no API field only for display convenience.
- Replace source-string link counting with DOM assertions for exactly eight
  destinations, expected hrefs, workspace retention, child parent selection,
  no locale/prototype controls, and no complete-offline copy.
- Add CDP tests for separated context states, four commands, Run/comparison
  navigation, retryability-dependent recovery, empty, controlled loading,
  first error, stale refresh failure, and recovery.
- Cover drawer focus entry/loop, Escape/backdrop/link close, inert removal,
  focus return, geometry, and page/scoped overflow.
- Run the seven golden scenarios and retain current/diff artifacts on failure.
- Run focused S-022 API/browser checks and a representative browser scenario
  for every later workbench Story. Docker lifecycle is not required for this
  static fixture-backed correction.

## Implementation Checklist

- [ ] Separate eight primary destinations from deep route metadata without
  changing URLs or downstream dispatch.
- [ ] Implement shared snapshot controller and complete context bar.
- [ ] Implement all Overview regions, commands, bounded formatters, and state
  transitions.
- [ ] Establish scoped UI-013 tokens/primitives, self-hosted typography, and a
  pinned licensed Lucide subset while retaining legacy aliases.
- [ ] Repair narrow drawer semantics, focus, inert handling, geometry, and
  overflow containment.
- [ ] Replace brittle screenshot-existence checks with controlled CDP golden,
  diff, semantic, and geometry evidence.
- [ ] Run focused and later-Story shell/CSS regressions; record artifacts and
  environment residuals in the run log.

## Open Questions

None.

## Approval

Approved by the S-022 repair `story-pipeline` invocation on 2026-09-13. The
pipeline may proceed directly to development without separate design approval.

## Change History

- **2026-09-12:** Created the initial just-in-time implementation design.
- **2026-09-13:** Replaced the pre-implementation plan with an approved repair
  design grounded in delivered code, exact UI-001/UI-002/UI-013 regions, the
  complete Overview projection, eight-destination shell correction, scoped
  visual primitives, and deterministic Chrome/CDP comparison evidence.
