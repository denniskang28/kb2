# Story Design: S-025 - Query Lab And Evidence UI

## Status

Approved for Story Pipeline parity repair.

## Story Contract Snapshot

- Story: `S-025`, confirmed 2026-09-11 and implemented 2026-09-13.
- Repair target: UI-reference parity with `docs/ui/kb_ui.zip` at UI-005,
  UI-008, and UI-013 without changing the delivered query-engine contract.
- Sources checked: current S-025 contract and design; exact adopted prototype
  regions; current Query Lab service, static client, fixtures, and tests; the
  delivered S-024 inspector contract; and S-027's downstream route/context
  contract.
- Material decisions requiring approval: None. This pipeline invocation
  authorizes the bounded presentation, fixture, and additive test work below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Recompose the existing preflight/submit controls as the left work pane. Preserve server-owned Profile/index eligibility, rotating preflight authority, external disclosure, and owner-authorized Stop. Pending requests disable relevant controls and replace stale submit authority; safe errors preserve user selections for retry. | Service/API regressions retain option, preflight, acknowledgement, single-use submit, and Stop rules. Browser tests cover initial, loading, validation/error, stale response, submit, polling, Stop, and unavailable options. |
| 2 | Render the returned frozen plan and ordered attempts as a compact stage table, then expose each returned retriever/fusion/rerank candidate set as a real tab with its own rows. Context decisions remain a separate ruled table and are associated only by returned chunk/stage identity. No candidates, scores, stage names, or durations are synthesized. | Fixtures cover independent retrieval sets, fusion, rerank, absent optional stages, failed attempts, real timing, and context inclusion/exclusion. DOM assertions prove tab separation and no raw JSON fallback in the primary UI. |
| 3 | Build the center Evidence pane from the returned Evidence projection: citation key, excerpt, document/chunk IDs, locator, contributors and bounded scores, hierarchy/table facts, context decision, and rationale. Citation and source commands call the unchanged `inspector(id, origin, selectedLocator)` entry point. | Browser tests activate candidate tabs, Evidence rows, citation commands, and source commands; assert exact selected-locator pairing, live locator summary, Escape, focus return, and preserved URL context at both widths. |
| 4 | Make the right pane's result band authoritative to `final.state`. `ANSWERED` alone may render answer text and citation controls. `CLARIFICATION_REQUIRED`, `ABSTAINED`, and `FAILED` render only the safe action. Verification and bounded repair appear below as trace detail and never as additional final states. | Contract tests retain the no-answer invariant for non-answered states. Four deterministic final-state fixtures are exercised at 1440 x 900 and 644 x 900, including verification failure, repair success, and repair exhaustion trace detail. |
| 5 | Keep the selected generation capability disclosure beside the preflight plan and require its acknowledgement exactly when returned by the server. Loading, readiness, and failure copy uses safe codes only; the browser performs no provider probe and makes no general offline/privacy claim. | Browser/API assertions cover local plans, external configured/unavailable plans, acknowledgement reset, retry after safe failure, and absence of credentials, endpoints, provider bodies, or unsupported answer fallback. |
| 6 | Establish a stable three-pane desktop hierarchy and a narrow stacked hierarchy using UI-013 tokens, dense ruled tables, zero-radius controls, restrained semantic color, and S-024's full-width narrow inspector. | Eight manifest-backed goldens cover all four final states at both target viewports. Geometry tests assert no document overflow or incoherent overlap, stable pane order, reachable controls, and scoped table scrolling. |

## Current Code Findings

- `QueryWorkbenchService` already owns safe options, preflight, single-use
  submission, cancellation ownership, ordered trace projection, candidate-set
  separation, Evidence parsing, final-response validation, and source Artifact
  resolution. Its existing response is sufficient for this parity repair.
- Stage rows expose `startedAt` and `endedAt` but no numeric duration. The UI may
  display the timestamps and may derive a duration only when both valid returned
  timestamps exist; an absent value is `不可用`, never zero or an estimate.
- Candidate rows are bounded stored payload rows, and context decisions are
  returned under `details`. Presentation may normalize known returned keys and
  join a decision to Evidence by exact `chunkId`; unknown shapes get a bounded
  unavailable row rather than a serialized object dump in the primary surface.
- The current browser surface is a single compact form followed by three simple
  sections. Candidate sets and trace details use `<details>/<pre>`, Evidence
  facts are raw JSON, final states have weak visual hierarchy, and loading/error/
  empty transitions are not modeled as durable regions.
- S-024 now provides the required 1080 px schema-conditional Artifact drawer,
  paired `.source-selected` nodes, an `aria-live` locator summary, keyboard tab
  behavior, inert background, Escape, focus return, and the public
  `inspector(id, origin, selectedLocator)` signature. S-025 must consume rather
  than fork it.
- Existing S-025 browser checks capture temporary screenshots only. They do not
  have a reviewed manifest/baseline, do not visually cover all authoritative
  final states, and do not validate the full three-pane hierarchy.

## Proposed Approach

### Stable Query Lab Hierarchy

Keep the native-DOM implementation and existing shell. Replace only the Query
Lab page body with this semantic structure:

```text
main.query-page
  header.title-row.query-title
  section.query-workspace[aria-label="Query Lab 工作区"]
    aside.query-control-pane
      question + Profile + indexed Artifact
      preflight/run/stop commands
      query-status[aria-live]
      resolved-plan + external disclosure
    section.query-retrieval-pane
      stage timing table
      candidate tablist / selected candidate table
      context-decision table
    aside.query-answer-pane
      authoritative final-state band
      answer or safe action
      Evidence list and citation/source commands
      verification/repair trace detail
```

At 1440 px, use fixed responsive tracks approximately
`minmax(280px,.8fr) minmax(430px,1.25fr) minmax(330px,1fr)`. The page regions
are flush ruled panes, not cards. Question controls and final status remain
visible near the top while each dense table owns its own horizontal overflow.
At 644 px the panes stack in the exact order control, retrieval, answer;
candidate/context tables scroll inside labelled containers and the document
itself never scrolls horizontally. Do not scale font sizes with viewport width.

### Controls, Authority, And Async State

The left pane continues to call the delivered endpoints. Options load into
native selects with a visible `role=status` loading region; empty Profile or
index catalogs get distinct empty states and cannot preflight. A preflight
request immediately invalidates the preceding token/submit controls and disables
the edited controls. Only the latest response may install new authority. A
changed question, Profile, or index clears the prior preview and external
acknowledgement before another preflight.

The resolved-plan section shows the returned digest and stage ID/kind/Plugin
rows in order. External stage/capability disclosure is visible before execution
and is bound to that token. Submit uses the returned acknowledgement rule, then
shows an announced pending state until a Run ID exists. Polling preserves the
last valid Run projection on a read failure and offers `重试读取`; Stop appears
only from `actions.stop`, becomes disabled while the request is pending, and is
not relabelled as retry/cancel after ownership ends.

Errors use `role=alert` and safe workbench codes. Input text and selections
remain available after a recoverable preflight/read error. No question, Profile,
index, answer, or Evidence fixture is stored outside existing controls and Run
contracts.

### Plan, Candidate, And Context Presentation

The stage table renders exact returned stage key, attempt, state/result, Plugin,
start/end or derived duration, and safe failure. Missing arrays are empty; an
absent scalar is `不可用`. State is conveyed by text/icon plus semantic tone.

Candidate tabs are native `role=tab` controls with `aria-selected`,
`aria-controls`, roving focus, Arrow Left/Right, Home, and End. Tabs exist only
for returned candidate artifacts and retain retrieval, fusion, and rerank
identity independently. The selected panel maps only present stored keys such as
rank, chunk ID, excerpt/text, safe score, locator, and contributors. Optional or
unknown facts show `不可用`; no browser fusion, rerank, threshold, score, or row
reordering is permitted.

Context decisions form a separate compact table using returned chunk ID,
source rank, decision reason, and safe score. A returned shortage gets its own
status strip with actual minimum/selected/token/reason facts. Decision rationale
may be shown next to an Evidence item only after exact chunk-ID association;
unmatched decisions remain visible in the context table.

### Evidence, Final State, And Inspector

Evidence rows use an unframed ruled list. Each row contains a citation-key
button when a source Artifact is available, excerpt, document/chunk identity,
exact locator summary, contributor IDs and stored bounded scores, structural
context, table element IDs, context decision, and rationale. Empty Evidence and
unavailable source identity are explicit and do not create a citation command.

The result header always displays exactly one authoritative final state:

- `ANSWERED`: answer text plus only validated returned citation keys;
- `CLARIFICATION_REQUIRED`: safe action only, styled as warning;
- `ABSTAINED`: safe action only, styled as neutral/warning;
- `FAILED`: safe action or bounded unavailable copy only, styled as failure.

Verification outcomes, missing citation keys, failure codes, and repair attempts
remain a subordinate trace band. An answered repair-success fixture may show
that history without renaming the final state. A verification-failed or
repair-exhausted fixture remains `FAILED` and renders no answer text.

Both final citation buttons and Evidence source buttons call the existing S-024
inspector with the exact `sourceArtifactId` and `sourceLocator`. Opening it must
retain the Query page and any S-027 diagnosis query string, mark exactly the
paired source nodes selected, move focus into the drawer, and restore focus to
the invoking button after Escape or close.

### Loading, Error, Empty, And Accessibility States

- Initial option loading, preflight pending, submit pending, and active Run
  polling use persistent `role=status`/`aria-live=polite` regions and do not
  resize the page controls.
- Validation, option, preflight, submit, polling, and source-unavailable errors
  have scoped `role=alert` regions and a relevant retry where authority allows.
- Empty Profile, index, candidate, context, Evidence, and trace collections have
  distinct labelled empty states; raw `[]`, `{}`, `null`, and object dumps do
  not appear as the primary presentation.
- Every command is a native button; controls have visible focus, hover, pressed,
  and disabled states. Tabs implement full keyboard selection. Status is never
  color only. Long IDs wrap in definition rows or scroll in their owned table.
- The page itself is not modal. S-024 alone owns inspector focus trap, inertness,
  Escape, scroll lock, and focus return; Query Lab must not add a second overlay
  controller.

## Relevant Impacts

- **UI:** Rebuild `queryLab()` into small render/state helpers and add Query-
  specific component styles that consume existing UI-013 variables. Keep the
  shell, route, native-DOM model, pinned Archivo/Lucide assets, and shared
  inspector selectors intact.
- **API/data:** No endpoint, durable data, engine, or migration change is
  required. The existing additive response fields remain authoritative. Timing
  display and Evidence/decision association are presentation of returned facts,
  not new query computation.
- **Security:** Continue text-node-only rendering. Never expose raw vectors,
  storage paths, prompts/provider payloads, credentials, or unsafe exceptions.
  External disclosure describes only the returned selected stages.
- **Compatibility:** Preserve current Query routes/endpoints, preflight token
  lifecycle, final-state validation, `inspector(id, origin, selectedLocator)`,
  S-024 source selectors, and S-027 URL diagnosis context/action routing.

## Deterministic Visual Contract

Create `tests/visual/baselines/s025/manifest.json` and eight reviewed PNGs:

| File | Fixture state | Required visible evidence | Viewport |
|---|---|---|---|
| `query-answered-1440.png` | `ANSWERED` after bounded repair | three panes, separate candidate tabs, context decision/shortage, validated answer, Evidence and citation/source controls, subordinate repair detail | 1440 x 900 |
| `query-answered-644.png` | same | stacked pane order, scoped tables, reachable citation, no page overflow | 644 x 900 |
| `query-clarification-required-1440.png` | `CLARIFICATION_REQUIRED` | safe action, relevant Evidence/decision facts, no answer/citation controls | 1440 x 900 |
| `query-clarification-required-644.png` | same | narrow hierarchy and no overlap | 644 x 900 |
| `query-abstained-1440.png` | `ABSTAINED` | shortage/abstention facts and safe action, no answer | 1440 x 900 |
| `query-abstained-644.png` | same | narrow hierarchy and no overlap | 644 x 900 |
| `query-failed-1440.png` | verification failure with exhausted bounded repair | failed trace detail and safe action, no answer/citations | 1440 x 900 |
| `query-failed-644.png` | same | narrow hierarchy and no overlap | 644 x 900 |

Fixtures must be contract-valid, use actual returned scores/timings/Plugin IDs,
and contain no prototype defaults. Loading, option/preflight error, empty
candidate/Evidence, external acknowledgement, Stop, tab keyboard behavior, and
inspector focus are interaction/DOM assertions rather than additional goldens.

The S-025 manifest records Story/UI anchors, prototype archive SHA-256, fixture
revision, every baseline SHA-256, and the exact capture conditions already
pinned by S-022/S-024: Chrome product/protocol/user agent/V8/Blink identity,
headless-new, GPU disabled, `zh-CN`, screen/light/no forced colors/no-preference
reduced motion, DPR 1, exact viewport, complete document, loaded local Archivo
400/600/800 resource timing, disabled animation/transition, transparent caret,
and PNG output. Use one persistent CDP target/session per capture so emulation,
readiness assertions, and screenshot share state.

Comparison decodes baseline/current PNGs to RGBA, requires identical dimensions,
marks a pixel changed when any channel differs by more than 12, and permits at
most `0.005` differing pixels. Tests never create or update baselines. On a
failure only, write current/diff PNGs under the test temp directory and report
ratio, dimensions, bounds, and paths. Baselines are refreshed only after manual
inspection and explicit manifest SHA update.

## Alternatives And Risks

- Adding a frontend framework or copying prototype inline markup was rejected;
  it would fork the delivered shell and import prototype-only behavior.
- Combining retrieval/fusion/rerank into one table was rejected because it
  erases provenance. Rendering candidate JSON was rejected because it makes the
  diagnostic hierarchy unusable and unstable.
- Adding product scenario controls was rejected. The visual harness selects
  fixture endpoints/Run IDs outside the product UI.
- Adding final states for verification or repair was rejected; those are trace
  details under the four `FinalResponse/v1` states.
- Visual drift from browser/font changes must fail capture prerequisites, not
  silently refresh a golden.

## Test Strategy

- Retain focused Query service/engine/API coverage for eligibility, question
  bounds, immutable plan, token rotation/single use, external acknowledgement,
  candidate/Evidence projection, final validation, polling, and owner-only Stop.
- Add native-DOM/browser assertions for the stable three-pane order, loading/
  error/empty states, stale-response rejection, all four final states, exact
  no-answer rule, candidate/context separation, keyboard tabs, and actual Stop.
- Exercise citation and Evidence source buttons against S-024 at both widths;
  assert exact locator pair/live summary, conditional tabs, drawer geometry,
  Escape/focus return, and S-027 query-string preservation.
- Capture and compare all eight manifest-backed scenarios only after exact
  viewport/font/resource/media/readiness assertions. Assert
  `documentElement.scrollWidth <= innerWidth`, positive-size controls, stable
  tracks/stack order, no incoherent bounding-box overlap, and overflow only in
  labelled table/drawer containers.
- Run focused S-025 tests, S-022 shell goldens, S-024 inspector/browser tests,
  S-026/S-027 consumer regressions, and the broader non-Docker workbench suite.

## Implementation Checklist

- [ ] Refactor Query Lab into explicit async state and three-pane render helpers.
- [ ] Render structured plan/stage, candidate-tab, context-decision, Evidence,
  final-state, and verification/repair regions from existing returned facts.
- [ ] Preserve and verify S-024 inspector and S-027 diagnosis compatibility.
- [ ] Add UI-013 responsive/accessibility styling without changing shell tokens.
- [ ] Add S-025 manifest, eight reviewed goldens, deterministic comparison, and
  focused interaction/geometry/regression coverage.

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-025/S-026 `story-pipeline` parity-repair invocation on
2026-09-13; no separate product, API, data, or architecture decision is needed.

## Change History

- **2026-09-13:** Created the initial just-in-time technical design and
  delivered the API-backed S-025 workflow.
- **2026-09-13:** Revised for UI-reference parity against UI-005, UI-008, and
  UI-013; specified the three-pane hierarchy, all authoritative final states,
  shared inspector behavior, and deterministic dual-viewport golden coverage.
