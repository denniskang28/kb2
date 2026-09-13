# Story Design: S-024 - Document, Ingestion Run, And Artifact UI

## Status

Approved for Story Pipeline parity repair.

## Story Contract Snapshot

- Story: `S-024`, confirmed 2026-09-11 and implemented 2026-09-13.
- Repair basis: the confirmed S-024 contract, the current implementation and
  executable tests, UI-003 (`isDocs`, `upOpen`), UI-004 (`isIng`), UI-005
  (`artOpen`), and UI-013. S-022 provides the already delivered shell, visual
  tokens, local Archivo faces, pinned Lucide subset, and deterministic visual
  harness.
- Repair boundary: visual and interaction parity plus the smallest additive
  preflight correction required to make the confirmed Profile disclosure true.
  Existing workbench API paths and fields remain valid; one candidate-selection
  path and optional response/request fields are added. Engine behavior,
  immutable-plan rules, S-022 navigation, and delivered S-025/S-027 behavior
  remain unchanged.
- Material decisions requiring approval: None. The Story Pipeline invocation
  authorizes this correction without a new product or API decision.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Replace the always-visible upload fields and raw preflight JSON with a Documents title/command surface and a compact modal workflow. File/Profile selection, detected facts, automatic resolution, evaluated rules, candidate Profiles, selected Profile, plan digest, and resolved stages render from the token-bound selection response. Changing the candidate performs a server-side explicit resolution and token rotation before it can be submitted. | Service/API tests prove automatic and explicit candidate previews have their own selected Profile, digest, stages, and disclosure; browser assertions cover initial dialog, automatic selection, explicit switch pending/success/failure, Profile-set preservation, matched-rule rationale, submit, Escape, focus trap/return, and both viewport sizes. |
| 2 | Render local persistence separately from a semantic warning containing only the currently selected candidate's returned `externalStages`. Confirmation remains disabled until that exact candidate preview succeeds and is acknowledged when required; no privacy, offline, or residency claim is added. Starting any fresh or candidate preflight immediately invalidates the old client result and token. | Service/API tests cover token replacement/rotation, selection mismatch, stale plan rejection, local-to-external and external-to-local switching, and acknowledgement against the selected disclosure. Browser tests prove pending/failure has no submit path and an automatic plan cannot be confirmed after selecting another candidate. |
| 3 | Recompose the existing ingestion projection as a Run header, selectable typed-stage rail, resolution/metrics pane, and persistent selected-stage inspector. Every stage value comes from `stages`, `resolution`, Run metrics, or Run quality; absent values get an explicit unavailable marker rather than invented configuration. | Browser assertions cover RUNNING, FAILED, SKIPPED, accepted fallback, automatic retry attempts, Plugin identity, input/output Artifacts, timing, metrics, quality, and structured failure. |
| 4 | Header actions render only when `actions.stop` or `actions.rerun` permits them. Repeated attempts remain trace evidence in the stage rail; no retry control or endpoint is introduced. Rerun keeps the existing fresh-preflight handoff. | Contract/source assertions retain the no-manual-retry invariant; browser tests cover action visibility, Stop reload, rerun handoff, and unchanged original Run identity/digest. |
| 5 | Rebuild the shared inspector as a large schema-conditional drawer with real tabs and stable-ID/source-locator synchronization. Canonical/tree, tables, chunks, raw text, metadata, and lineage each use only fields already returned by the existing Artifact endpoint; producer `runId` and `pluginId` remain separately structured, and table selection updates the same live locator summary as Canonical/Chunk selection. Unsupported content shows a bounded unavailable state and raw vectors remain absent. | Service tests retain exact IDs/locators and producer fields. Browser tests cover tab semantics, Canonical/table/Chunk source selection in both directions with live summary changes, structured producer display, selected-locator handoff from S-025, conditional tabs, Escape, focus return, and no raw vectors. |
| 6 | Use the S-022/UI-013 tokens for dense ruled surfaces at exact 1440 x 900 and 644 x 900 captures. Add six reviewed S-024 goldens and a non-mutating RGBA comparison gate. | Golden comparisons cover UI-003, UI-004, and UI-005 at both sizes; geometry assertions cover viewport, scoped overflow, dialog/drawer fit, stage rail, controls, and non-overlap. |

## Current Code Findings

- The engine-facing S-024 implementation is authoritative for resolution and
  execution. Initial preflight resolves the automatic choice and stores only
  that automatic evidence in `_Preflight`; `submit()` then re-resolves an
  explicitly supplied Profile. Therefore an alternate candidate can currently
  be submitted after the UI displayed the automatic candidate's stages and
  disclosure. The current API has no way to preview an alternate candidate
  from the retained bytes, and this correctness gap requires the additive
  selection contract below.
- `documents()` currently places Profile ID, native file input, and Preflight
  directly below the page heading. Its result is one unstructured JSON
  `<pre>`. There is no upload dialog, step/state hierarchy, detected-fact grid,
  matched-rule explanation, resolved-stage preview, or stable error region.
- The adopted dense historical document list cannot be populated by the
  current API. Prototype rows are explicitly synthetic. This repair therefore
  treats the page as a submission workbench: it shows an honest empty/current
  submission state and puts the complete API-backed intake in the modal. It
  does not fabricate a persisted document catalog or add an endpoint.
- `runs()` currently renders an UUID lookup beside a sequence of expanding
  `.stage-row` blocks, each containing a full JSON `<pre>`. It does not expose
  stage selection, typed visual flow, Run identity hierarchy, resolution tabs,
  or a persistent selected-stage inspector. Unavailable action text adds noise
  even though the Story says unsupported actions must not appear.
- `inspector()` currently uses a 620 px padded drawer. All object views are the
  same button list, tab controls have no tab state, tables are not rendered as
  tables, metadata is a JSON dump, lineage is a sentence, and source facts are
  serialized into button labels. The stable-ID pairing works and is reused by
  S-025, so that synchronization contract must be preserved while changing
  presentation.
- `artifact.css` duplicates colors and narrow drawer geometry instead of the
  S-022 tokens. `workbench.css` already supplies Archivo 400/600/800, UI-013
  semantic colors, zero radii, focus styles, 220 px navigation, and the below
  900 px breakpoint; the repair should consume those shared primitives.
- Current S-024 browser tests capture screenshots into temporary directories
  but do not compare them with reviewed baselines. They also use fixed ports
  for two scenarios and do not pin device metrics, media, fonts, locale, or the
  exact Chrome build as the mature S-022 visual harness does.

## Proposed Approach

### Client Structure And State

Keep the dependency-free native DOM implementation. Split the large inline
renderers into focused client helpers in `workbench.js`; no build tool or UI
framework is introduced:

- `createDialogShell(...)` owns overlay, labelled panel, close icon, focus
  trap, Escape, inert background, and focus return. It keeps its own origin;
  it must not reuse the S-022 navigation drawer's global trigger.
- `renderStatus(...)`, `renderDefinitionRows(...)`, and
  `renderArtifactAction(...)` reuse S-022 status tokens and safe text-node
  rendering.
- `renderDocumentPreflight(...)`, `renderIngestionRun(...)`, and
  `renderArtifactTab(...)` are pure DOM composition over existing response
  objects. They never use `innerHTML` or infer engine decisions.
- One local state object per surface tracks only UI state: selected file,
  preflight generation, token-bound result, selected explicit Profile,
  acknowledgement, selected stage, and selected Artifact tab/stable locator.
  No raw bytes or API result is persisted to `localStorage`; the existing
  rerun object remains the sole short-lived `sessionStorage` handoff.

All asynchronous surfaces have deterministic `loading`, `populated`, `empty`,
and `error` regions. Before a fresh preflight or candidate-selection request is
sent, the client increments a request generation, clears the old token/result/
acknowledgement, removes or disables Submit, and renders only the pending state.
A late response from an older generation is ignored. Failure leaves the dialog
open and writes the safe error into `role="alert"`, but does not restore the old
result or a submit path. Candidate controls are disabled while selection is
pending, preventing concurrent rotations.

### Token-Bound Candidate Preview

Make the smallest backward-compatible extension to the existing preflight
contract:

1. `PUT /api/workbench/documents/preflight` keeps its body and required headers
   unchanged and accepts optional `X-Replaces-Preflight-Token`. When present,
   the service removes that old token before reading/resolving the new request;
   this remains true when the replacement request fails. Existing clients that
   omit the header behave as before.
2. Add `POST /api/workbench/documents/preflights/{token}/selection` with the
   bounded JSON body `{ "profileId": "..." }`. The service atomically claims
   and removes the old token before awaiting explicit resolution against the
   same retained bytes and workspace Profile set. The ID must be one of the
   server-returned `automatic.candidateProfileIds`; arbitrary inner Profile or
   Plugin selection is rejected. Success returns a newly generated token;
   failure leaves no confirmable token.
3. Both initial and selection responses keep
   `workbench-document-preflight/v1` and all existing top-level fields. Add
   `selection: { profileId, selectionTier }`; on every response the top-level
   `planDigest`, `stages`, and `disclosure` describe this `selection`, while
   `automatic` continues to describe the original deterministic match and
   rationale. Thus current automatic-only clients remain compatible, while a
   repaired client can distinguish automatic evidence from the preview it is
   confirming.
4. Extend `_Preflight` with the token-bound `selected_profile_id`,
   `plan_digest`, and selected disclosure snapshot. `submit()` accepts an
   omitted `profileId` as the bound selection for compatibility, rejects a
   different supplied value as `PREFLIGHT_SELECTION_MISMATCH`, and recomputes
   the selected plan immediately before execution. If its digest or external
   disclosure differs from the confirmed snapshot, consume the token and
   return `PREFLIGHT_STALE`; no Run is created. Missing required acknowledgement
   remains correctable without consuming an otherwise current token.

This is not a new resolution policy. It exposes the existing resolver's
explicit-profile branch before execution and binds confirmation to the facts
the operator actually saw. It introduces no persisted upload, Profile version,
or arbitrary Plugin selection.

### Documents And Upload Dialog

The Documents route DOM is:

```text
main.documents-page
  header.title-row.documents-title
    title + concise API-owned purpose
    button.command-primary [upload icon] 上传并预检
  section.documents-surface
    header.section-header 本次提交
    div.document-current | div.empty-state | div.notice-failure
  div.modal-backdrop
    section.upload-dialog[role=dialog][aria-modal=true]
      header.dialog-header
      div.upload-dialog-body
        section.upload-source-step
        section.preflight-facts
        fieldset.profile-resolution
        section.resolved-stages
        section.persistence-disclosure
      footer.dialog-actions
```

The page does not pretend to list persisted Documents. Before selection it uses
the standard empty state; after a local file is chosen or a rerun source is
received, `document-current` uses one dense ruled row with real filename/source
Artifact, media type/extension, size, selected Profile, plan digest, and current
preflight status. Browser-selected filenames are local presentation state, not
new engine facts.

`上传并预检` opens a centred panel of `min(760px, calc(100vw - 32px))` at
desktop. The first section uses an explicit labelled file input and Profile-set
field; rerun preflight skips file selection and labels the returned immutable
source Artifact. Preflight facts are definition cells with only implemented
detector keys. Profile candidates use native radio controls so automatic
selection and explicit override are legible together. The automatic choice is
annotated with selection tier and evaluated matched/unmatched rules. Selecting
a different radio immediately removes the old resolved stages/disclosure and
Submit, calls the candidate-selection endpoint, then renders only the rotated
token's `selection`, digest, stages, and disclosure. The automatic rationale
remains visible as provenance but is clearly labelled separately from the
explicit selection. Resolved stages are compact rows containing stage key and
returned candidate Plugin IDs; the plan digest is a wrapping monospace value.

Local persistence is a neutral notice using `localPersistence`. Non-empty
`externalStages` render an amber warning list of stage, Plugin, capability, and
message followed by the acknowledgement checkbox. The primary `创建新 Run`
button remains disabled until preflight succeeds and any required disclosure is
acknowledged. Cancel/close never submits. Successful submission retains the
existing redirect to `/workbench/runs?run=<id>` and all current query context
rules. Starting a new file/Profile-set preflight passes the prior token through
`X-Replaces-Preflight-Token`; the UI has already invalidated that token before
the request begins. Submit sends only the Profile bound by the latest successful
response and is absent in pending/error states.

At 644 px the modal is inset 8 px, max-height `calc(100dvh - 16px)`, and uses a
fixed header/footer with one internally scrolling body. Fact cells become two
columns and then one where text requires it; action buttons wrap without
changing height. The background shell is inert and cannot scroll while open.

### Ingestion Run Stage Flow And Inspector

When a `run` query parameter is present, replace the generic Runs title with a
compact `ingestion-run-header`: `Ingestion Run`, wrapping Run ID, semantic Run
status, plan digest, timestamps, and only permitted Stop/Rerun commands. The
manual UUID lookup remains as a narrow fallback when the route has no selected
Run; it is not shown beside a loaded Run.

The loaded Run DOM is:

```text
article.ingestion-run[data-run-state]
  div.ingestion-stage-rail[role=list]
    div.stage-node[role=listitem]
      button.stage-card[aria-pressed]
      span.stage-connector[aria-hidden]
  div.ingestion-detail-grid
    section.run-plan-pane
      div.run-tabs[role=tablist]
      div.run-tab-panel[role=tabpanel]
    aside.stage-inspector[aria-live=polite]
      header.stage-inspector-header
      dl.stage-facts
      section.stage-artifacts
      section.stage-quality
      div.stage-failure[role=alert]
```

Each attempt is a distinct 124 x 64 stage card, preserving API order and
`stageKey #attempt`. Left border and icon/tag use the semantic state mapping:
success teal, running/retrying blue, skipped/fallback warning amber, failed red,
and unknown/pending neutral. `selection` is displayed independently as
accepted/rejected/fallback evidence; it never rewrites `state` or `result`.
The initial selection is deterministic: first failed attempt, else active
attempt, else final recorded attempt. Click and Enter/Space select a card.

The left pane tabs expose only facts the Run projection owns: resolution,
Run-level metrics/quality, and immutable identity. Resolution uses definition
rows for selected Profile/tier, observables, candidate IDs, and evaluated rules
from `resolution`; it does not label missing plan JSON as a resolved plan.
The selected-stage inspector shows Plugin, attempt, state/result/selection,
start/end/duration when derivable from returned timestamps, safe summary,
inputs, outputs, metrics, quality signals, and structured safe failure.
Artifact outputs remain buttons and invoke the shared inspector. Missing arrays
are treated as empty and missing scalar facts as `不可用`, keeping every state
renderable without exceptions.

At desktop the rail wraps within a white ruled band and the detail area uses
`minmax(360px, 1.1fr) minmax(360px, .9fr)`. At 644 px the rail is a single
horizontal, keyboard-scrollable lane with its own overflow; the detail panes
stack and only JSON/definition content scrolls internally. No page-level
horizontal overflow is allowed.

### Artifact Inspector And Source Synchronization

Preserve the public client entry point `inspector(id, returnFocus,
selectedLocator)` because S-025 and S-027 call it. Replace its internals with:

```text
div.artifact-overlay
  div.artifact-scrim
  aside.artifact-inspector.inspector-drawer.open[role=dialog]
    header.artifact-header
      identity + schema status + close icon
    div.inspector-tabs[role=tablist]
      button[role=tab][aria-selected][aria-controls]
    section.inspector-body[role=tabpanel]
      schema-specific content
```

The desktop panel is right-aligned, full height, and
`width: min(1080px, calc(100vw - 220px))`; the shell remains visible behind a
42% ink scrim. At 644 px it is 100vw, with header and tabs fixed and the panel
body scrolling. Header identity wraps rather than ellipsizing the only copy of
the Artifact ID. Opening does not change the URL, route filters, or selected
Run. Closing by Escape or the icon removes inert state and returns focus to the
exact invoking control.

Tabs are created only from `view.tabs`, in server order, with stable localized
labels and no disabled/fake tabs. Arrow Left/Right, Home, and End move focus and
selection within the tablist. Every tab has a labelled unavailable/empty state.

- `raw`: bounded `rawText` in a labelled monospace preview. If unavailable,
  show the returned reason; never synthesize binary content.
- `canonical` and `tree`: split stable-object list and source-locator pane.
  Tree indentation is presentational only when parent structure is returned;
  otherwise both use a flat exact element list rather than inventing hierarchy.
- `table`: render each returned table identity/locator and its real cell array
  in a scoped horizontal table viewport. Preserve span/row/column facts when
  present; do not infer merged cells.
- `chunks`: dense rows for chunk ID, bounded text, source element IDs, and each
  citation. Selecting any citation keeps the chunk and exact citation locator
  distinguishable; no first-citation shortcut is allowed.
- `metadata`: ruled key/value rows for the safe manifest projection, metrics,
  and quality. It excludes storage locators and raw content.
- `lineage`: ordered producer, current Artifact, and returned parent IDs. The
  existing `producer` object is rendered as two separately labelled values,
  `Run ID` from `producer.runId` and `Plugin ID` from `producer.pluginId`, never
  as serialized object text or `[object Object]`. Missing fields have distinct
  unavailable values. It is lineage, not a user-facing version timeline;
  parent content is not fetched recursively.

For Canonical/table/Chunk objects, retain the established pairing invariant:
the object control and its source locator control share the same
`data-stable-id`, with the full locator in `data-locator`. Selecting either
adds `.source-selected` to exactly that pair and updates an `aria-live` locator
summary. `selectedLocator` from a Query citation activates the exact matching
returned locator after the initial tab renders. With no raw source renderer in
the current API, the source pane is an honest locator sheet showing kind,
page/sheet/slide/section and exact coordinates or cell ranges; it must not draw
a synthetic document page. A table identity control and its locator control use
the same selection helper as Canonical/Chunk pairs, so selecting either updates
the same `aria-live` summary with the exact table ID and locator; rendering the
cell grid alone is not considered table/source synchronization.

### Shared Visual Language

S-024 adds only semantic component classes to `workbench.css` and
`artifact.css`; all colors, type, spacing, focus, and status styling resolve to
the S-022/UI-013 variables. The repaired surfaces use Archivo, 22/19 px page
titles, 10-13 px compact labels, neutral ground, white working panes, 1 px soft
rules, 2 px structural rules, zero radii, red primary commands, and existing
teal/blue/amber/red state colors. Reuse the pinned Lucide icons already present
(`upload`, `play`, `close`, `refresh`, `check`, `clock`, `alert`, `arrow`,
`file`); if implementation needs another icon, update the pinned Lucide
manifest and license provenance in the same delivery.

Major page regions remain unframed bands or split panes. Do not introduce
cards, decorative imagery, gradients, shadows except the adopted modal depth,
or viewport-scaled typography. Long UUIDs, digests, Plugin IDs, locator JSON,
and Chinese labels wrap or scroll only in their owned pane.

## Deterministic Visual Contract

Create `tests/visual/baselines/s024/manifest.json` and six reviewed PNGs:

| File | UI anchor | Fixture state | Viewport |
|---|---|---|---|
| `documents-preflight-automatic-1440.png` | UI-003 | upload dialog after successful automatic match, detected facts and local disclosure visible | 1440 x 900 |
| `documents-preflight-automatic-644.png` | UI-003 | same state with fixed dialog chrome and stacked content | 644 x 900 |
| `ingestion-state-matrix-1440.png` | UI-004 | RUNNING Run containing failed first attempt, accepted retry/fallback, skipped stage, active stage, and selected failure inspector | 1440 x 900 |
| `ingestion-state-matrix-644.png` | UI-004 | same state with horizontal stage rail and stacked details | 644 x 900 |
| `artifact-canonical-source-1440.png` | UI-005 | Canonical tab with selected stable object/source locator pair | 1440 x 900 |
| `artifact-canonical-source-644.png` | UI-005 | same synchronized selection in full-width narrow drawer | 644 x 900 |

The four review repairs do not add a seventh visual composition: candidate
switching reuses the same UI-003 dialog geometry, structured producer belongs
to the existing inspector tabs, and table/live-summary selection does not alter
the canonical golden state. Cover local-to-external candidate switching,
pending/failure submit removal, Lineage, and Table at both widths with DOM,
geometry, and interaction assertions. If the repaired automatic dialog or
Canonical default pixels change, update only the affected existing baseline
after explicit human inspection and its manifest SHA refresh; tests still never
update goldens automatically.

The S-024 manifest owns its baseline names, fixture revision, prototype archive
SHA-256, UI anchors, per-file SHA-256, and full capture conditions. It pins the
same verified conditions as S-022: exact Chrome product/protocol/user agent/V8/
WebKit identity, headless-new, disabled GPU, `zh-CN`, screen/light/no forced
colors/no-preference reduced motion, DPR 1, exact viewport, loaded Archivo
400/600/800 resources, complete document readiness, disabled animation/
transition, transparent caret, and PNG output.

Generalize the existing S-022 helpers so S-022 and S-024 both call one manifest-
driven capture/comparison implementation; do not weaken or rewrite S-022
baselines. The comparison decodes both PNGs through Chrome to RGBA, requires
identical dimensions, marks a pixel changed when any channel differs by more
than 12, and passes only at a differing-pixel ratio at or below `0.005` (0.5%).
Tests never create or update a reviewed baseline. On failure only, write
`<stem>-current.png` and `<stem>-diff.png` under the test temporary directory
and report ratio, dimensions, bounds, and diagnostic paths.

Use dynamic free localhost ports and the isolated Chrome lifecycle helpers.
Capture only after fixture state, dialog/drawer selection, exact viewport,
fonts, resource timing, locale/media, and stabilization assertions pass.

## Relevant Impacts

- **API/data:** One additive candidate-selection endpoint, one optional
  replacement-token request header, an optional `selection` response object,
  and token-bound preview fields in the in-memory `_Preflight` record. Existing
  initial preflight/submission paths and fields remain valid. There is no
  database, trace, Artifact, Profile, or migration change.
- **Security:** Continue text-node-only rendering. File bytes remain confined
  to the current raw-body preflight request; no new client persistence, path,
  credential, provider body, storage locator, raw vector, or unsafe error is
  exposed.
- **Accessibility:** Two true modal surfaces own inert state, labelled close
  controls, focus trap/return, and Escape. Stage selection uses native buttons
  and `aria-pressed`; Artifact tabs use the tabs pattern; state is never color
  only; loading/error updates use `aria-live`/`role=alert`.
- **Compatibility:** S-022 shell selectors and breakpoint stay intact. The
  shared `inspector(id, origin, selectedLocator)` behavior and synchronization
  selectors remain compatible with S-025 citations and S-027 Artifact links.

## Alternatives And Risks

- Adding a document-list API was rejected because this is a parity correction
  and the current Story implementation has no persistent document catalog.
  Synthetic prototype rows are not authoritative product data.
- Re-uploading the raw file through `PUT` on every candidate switch was
  rejected because rerun preflights may originate from an immutable source
  Artifact with no browser `File`, and repeated upload expands data handling.
  Token-bound selection reuses the already bounded in-memory source and rotates
  authority instead.
- Fabricating a PDF/page preview from locator rectangles was rejected. The
  current endpoint supplies exact locators but no source renderer; a truthful
  locator sheet preserves traceability without imitating document content.
- Copying the prototype's inline HTML/CSS or adding a framework was rejected;
  it would fork the delivered shell and import demo-only behavior.
- A single global modal trigger risks returning focus to the wrong surface
  after the navigation drawer, upload dialog, and Artifact inspector interact.
  Each overlay therefore owns its origin and teardown while sharing only small
  focus utilities.
- Exact visual tests are sensitive to browser/font drift by design. A mismatch
  is a failed capture prerequisite, not permission to refresh baselines.

## Test Strategy

- Retain the existing S-024 service/API tests for bounds, token lifecycle,
  automatic/explicit resolution, external disclosure, immutable rerun, Run
  projection, action authority, Artifact schema gating, and exact locators.
  Add service/API cases proving candidate selection consumes the prior token,
  returns a new token and candidate-specific digest/stages/disclosure, preserves
  automatic rationale separately, rejects unknown/expired/concurrently claimed
  tokens, rejects submit selection mismatch, and creates no Run after a stale
  digest/disclosure check.
- Replace brittle assertions tied to raw JSON layout only where the new DOM
  deliberately changes. Add focused DOM/browser assertions for all classes,
  ARIA relationships, status labels, conditional controls, and missing-field
  states described above.
- Exercise UI-003 local and external workflows at both widths, including
  automatic local preview followed by an explicit external candidate preview,
  reset acknowledgement, candidate-specific stages/disclosure, and submission
  of only the rotated token. Assert fresh preflight and candidate switch remove
  old result/token/Submit synchronously; pending, failed, stale, and late prior
  responses never regain a submit path. Retain submission navigation, Escape,
  focus loop/return, background inertness, and modal scroll containment.
- Exercise UI-004 at both widths with failed, accepted retry/fallback, skipped,
  and running attempts. Assert deterministic initial selection, click/keyboard
  selection, inspector facts, safe failure, Artifact commands, Stop/Rerun
  capability visibility, and absence of manual Retry.
- Exercise UI-005 at both widths for Canonical/source bidirectional selection,
  table and multi-citation Chunk rendering, metadata, lineage, unavailable
  content, conditional tabs, exact selected-locator handoff, tab keyboard
  navigation, Escape/focus return, and URL-context preservation. Assert Lineage
  exposes separately labelled producer Run/Plugin values without object
  serialization, and selecting either a table identity or source control gives
  exactly two `.source-selected` nodes and updates the same live locator summary
  to the exact table ID/locator.
- For all six golden states assert exact 1440 x 900 or 644 x 900 at DPR 1,
  `documentElement.scrollWidth <= innerWidth`, positive-size visible controls,
  no incoherent bounding-box overlap, and overflow only in labelled stage,
  table, dialog-body, or drawer-body containers.
- Run focused S-024 unit/contract/browser tests, then S-022 shell goldens,
  S-025 Query/citation browser tests, S-027 Runs/diagnosis browser tests, and
  the broader non-Docker workbench suite. The known Docker Compose startup
  limitation is unrelated to this static UI correction.

## S-025 And S-027 Regression Surface

- S-025 invokes the same inspector with `selectedLocator`; the exact locator
  must still select two paired nodes and the Query route/context must survive
  open/close. Citation, Evidence, final-state, and Query layout code is not
  restyled beyond shared selector compatibility.
- S-027 opens the inspector from mixed Run history and owns the public
  `/workbench/runs` list/detail route. Preserve its URL filters, selected Run,
  `.artifact-inspector`, `.source-view`, `.source-selected`, and action routing.
  The dedicated ingestion presentation activates only for the existing
  `?run=<id>` context without `runType`, `runState`, or `q`.
- S-022 owns navigation, context bar, shell loading, fonts, tokens, and its seven
  baselines. S-024 may consume and generalize test helpers but may not alter
  those visible contracts or accepted pixels.

## Implementation Checklist

- [ ] Add token-bound candidate preview/rotation and replacement semantics,
  retaining backward compatibility for the existing automatic preflight and
  submit paths.
- [ ] Refactor Documents into the title/current-submission surface and modal
  preflight workflow; invalidate stale client authority at request start and
  render/confirm only the latest candidate-specific preview.
- [ ] Build the typed ingestion Run header, selectable stage rail, resolution
  pane, stage inspector, capability-gated actions, and narrow layout.
- [ ] Rebuild the shared schema-conditional Artifact drawer while preserving
  its callable signature and stable source synchronization contract.
- [ ] Add S-024 component/responsive styles using only S-022/UI-013 tokens and
  the pinned icon/font assets.
- [ ] Generalize the manifest-driven visual helper without changing S-022
  behavior; add six S-024 baselines, manifest, interaction/geometry assertions,
  and failure diagnostics.
- [ ] Run focused and downstream S-022/S-025/S-027 regressions, inspect both
  viewport captures, and record evidence in the Story Pipeline run log.

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-024 `story-pipeline` parity-repair invocation on 2026-09-13;
no separate product, API, or architecture decision is required.

## Change History

- **2026-09-13:** Created the initial just-in-time technical design and
  delivered the API-backed S-024 workflow.
- **2026-09-13:** Revised for UI-reference parity against UI-003, UI-004,
  UI-005, and UI-013; retained the existing API and downstream contracts while
  specifying deterministic S-024 golden coverage.
- **2026-09-13:** Repaired final-review gaps by binding explicit candidate
  selection to a rotated preflight preview, invalidating stale submit state,
  structuring producer lineage, and applying live locator synchronization to
  tables.
