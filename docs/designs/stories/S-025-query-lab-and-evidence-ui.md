# Story Design: S-025 - Query Lab And Evidence UI

## Status

Approved for Story Pipeline workspace/information-density parity repair.

## Story Contract Snapshot

- Story: `S-025`, confirmed 2026-09-11 and implemented 2026-09-13.
- Repair base: `main@aa584cc`; delivery branch
  `feature/s-025-query-lab-workspace-parity`.
- Repair target: recompose the delivered Query Lab into the adopted fixed,
  dense diagnostic workbench hierarchy from UI-008 and UI-013 without changing
  the Query engine, persisted data, or delivered workbench read projection.
- Exact sources checked: the S-025 contract; `docs/ui/reference.md#UI-005`,
  `UI-008`, and `UI-013`; prototype `isQuery` at archive entry line 778 and
  `artOpen` at line 1451; current Query workbench service/client/styles;
  Query/browser tests and S-025 visual manifest; S-024 Inspector behavior;
  S-027 diagnosis-route context; S-028 document-submission persistence; and
  the viewport, pane-scroll, compact-toolbar, and drawer patterns delivered for
  the current Plugin Registry.
- Material decisions requiring approval: None. The user's instruction to apply
  the recommended bounded repair authorizes this design and immediate
  development.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Preserve the delivered single eligible Search Artifact and Query Profile selectors and the explicit `preflight -> disclosure acknowledgement when required -> create Run` sequence. Recompose them as one compact command surface with one red current-step command, persistent status, and the owner-authoritative Stop action; never submit automatically or bypass preflight. | Existing service/API authority tests remain green. Browser tests retain option loading/empty/error, stale invalidation, local-only versus external disclosure, submit failure/retry, polling, Stop, terminal cleanup, and requested S-027 Run context while asserting the compact command states. |
| 2 | Move the ordered resolved-stage summary into the control pane as dense status/stage/Plugin/duration rows. Candidate tabs show only `retrieval.candidate.set` stages, include returned row counts, and use a narrow raw-candidate table. Fusion, rerank, and context render once in the separate server-returned `decisionPath`; the browser formats returned cells but never joins, scores, thresholds, or reorders them. | Browser tests prove the stage summary remains ordered, only Retriever tabs appear with correct counts and roving focus, fusion/rerank are absent from the tablist but present in the decision table, selected/dropped decisions are visible, and a fixture mutation of returned path values is rendered verbatim. Existing projection unit/API tests retain exact-identity and no-vector guarantees. |
| 3 | Reorder the answer pane to `Answer + final status -> answer/action -> citation key + friendly locator -> visible verification summary -> EvidenceSet`. Render each actual Evidence item as a bounded repeated diagnostic entry with document, context status, excerpt, locator, contributors, rationale, and distinct source-preview action; retain UUIDs and structured facts in native details. Candidate-only dropped rows stay exclusively in the decision table and are never converted to Evidence. | Browser tests distinguish answer citation and Evidence preview commands, assert citation labels include locator, verify S-024 Inspector synchronization/focus/Escape/URL preservation, and prove an excluded decision row is absent from `.evidence-row` content. Non-answered states retain source preview but no answer/citation command. |
| 4 | Continue rendering exactly `ANSWERED`, `CLARIFICATION_REQUIRED`, `ABSTAINED`, or `FAILED` as product final states. Show the latest returned Verification outcome and attempt count in a compact always-visible summary immediately after the result, with ordered repair/verification facts in collapsed details; infer no status from final-state color or client logic. | The seven-scenario browser matrix covers fact, table, hierarchy, clarification, abstention, successful repair, and repair exhaustion; assertions retain the no-answer/no-citation invariant and returned verification ordering. |
| 5 | Keep external generation disclosure visible before the create-Run command whenever preflight returns external stages. Compactness may collapse plan identity and attempt diagnostics only after authority changes; it may not hide an unacknowledged boundary, credentials, provider bodies, paths, raw payloads, or vectors. | Existing preflight disclosure and recursive safe-response tests remain green. Browser geometry checks prove the disclosure, acknowledgement, and blocked create command are simultaneously reachable without overlapping or escaping the control pane. |
| 6 | On desktop, use a viewport-bound page and approximately `28% / 40% / 32%` control/retrieval/answer tracks with independent vertical scrolling. Remove blanket pane padding in favor of compact ruled bands. Retain below-900 px stacking and document scrolling. Keep the fourteen reviewed 1440/644 goldens, refresh them for the new composition, and add non-golden 1280/900 boundary geometry tests. | Visual comparison retains all fourteen scenario captures. Geometry/accessibility tests cover exact 1440/1280/900 desktop containment and proportions, independent pane scrolling, first-view visibility, scoped table overflow, the 644 stacked order, positive target sizes, and no incoherent overlap or document-level horizontal overflow. |

## Current Code Findings

- `QueryWorkbenchService` already owns Profile/index eligibility, rotating
  single-use preflight, external acknowledgement, Run/Stop authority, ordered
  Trace reading, typed Artifact validation, exact pinned-index joins,
  lineage-proven source resolution, final-response validation, and bounded safe
  projection. No service, API, repository, engine, or durable data change is
  needed for this repair.
- `workbench-query-run/v1` already returns stage `durationMs`, candidate
  Artifact type and rows, safe document/excerpt/locator display facts, the
  exact server-owned `decisionPath`, Evidence, context/verification detail, and
  validated final response. The client can distinguish Retriever stages through
  `candidate.artifact.artifactType === "retrieval.candidate.set"` without
  inventing a new stage taxonomy.
- The page currently places all ordered Trace rows, all retrieval/fusion/rerank
  candidate sets, the decision path, attempt detail, and Context Shortage in the
  middle pane. This repeats fusion/rerank information, forces a 760 px table in
  a roughly 500 px pane, and delays the authoritative decision path.
- The control pane keeps a large textarea, wide status notice, full digest,
  preflight stage table, disclosure, and submit action in normal document flow.
  At 1440 x 900 the plan extends below the first viewport and competes with the
  retrieval/answer story rather than acting as a compact control rail.
- The answer pane separates status, answer, Evidence, and Verification into
  successive blocks. Citation commands omit the already returned locator;
  Verification is below all Evidence and collapsed; Evidence facts are spread
  across an unframed row and a definition list. This preserves correctness but
  misses UI-008's glanceable answer-to-proof hierarchy.
- `.query-workspace` uses minimum pixel tracks and only a minimum height. The
  document therefore owns long vertical scrolling instead of the three panes,
  so controls, candidate decisions, and answer proof cannot remain visible
  together. In contrast, the newly delivered Registry establishes a correct
  `100dvh -> minmax(0, 1fr) -> scoped overflow` pattern.
- Registry's viewport containment, stable scrollbar, compact toolbar, and
  full-height drawer patterns are reusable. Its 1420/1300 px minimum data table
  is Registry-specific and unsuitable for Query Lab's middle pane.
- The fourteen S-025 goldens now cover seven contract-valid result scenarios at
  1440 and 644 px. The fixture still exposes route tokens such as
  `fact-answered` in the visible question, provides only one raw Retriever set,
  and does not visually prove simultaneous selected and dropped decision rows.

## Delivered Diagnostic Projection (Preserved)

The following read-projection, identity, lineage, Evidence, final-state, and
security decisions were delivered by the previous repair and remain normative.
This repair changes their presentation only. Where placement, pane proportions,
candidate-tab membership, visual fixtures, or viewport behavior differ, the
later `Workspace And Information-Density Repair` section supersedes the older
presentation baseline.

### Workbench Projection Boundary

Keep all new behavior in the read-only workbench projection. Additive changes
are allowed in `workbench/query.py`, its repository lookup dependency, and the
`workbench-query-run/v1` JSON response. Do not change Query Profile compilation,
`QueryEngine`, candidate/Evidence/final contracts, Artifact bytes, Run Trace
writes, database tables, or migrations.

For each completed Run projection:

1. Parse each candidate/Evidence/final Artifact with its existing typed
   contract and fail that individual diagnostic surface closed if invalid.
2. Resolve the one pinned Search Artifact from the typed index binding present
   in the candidate/Evidence contract, require it to match the Run plan/input
   binding, and parse `SearchIndexResult/v1` once per request.
3. Build an in-memory map keyed by `(document_id, chunk_id)` from the index's
   documents. A candidate enriches only on an exact identity match. There is no
   fuzzy locator/text match and no browser-side join.
4. Resolve source Artifact identity through the existing bounded lineage walk.
   Batch the distinct, proven source IDs through an exact repository lookup for
   S-028 document-submission display metadata. Never page the whole catalog to
   guess a match.
5. Return bounded display facts and the decision-path projection; discard the
   parsed embedding arrays and never serialize them.

The repository addition is read-only, for example
`get_document_submissions_by_source_ids(ids)` with deduplicated IDs, a hard cap
matching the bounded Evidence/candidate surface, and one parameterized query.
It returns only `DocumentSubmissionRecord` rows for exact source IDs. This is an
additive repository API over the S-028 table, not a durable-schema change.

### Safe Candidate And Evidence Display Facts

Candidate rows gain only projection fields derived from trusted artifacts:

```text
documentId       exact typed index identity
documentLabel    sanitized S-028 display filename or safe fallback
excerpt          bounded normalized prefix of SearchDocument.keyword_text
locatorLabel     friendly summary of the first exact typed locator
locators         existing bounded structured locators
```

Normalize runs of whitespace in `keyword_text` and truncate by Unicode code
points to a single documented display bound (target 280 characters), adding a
plain ellipsis marker only when truncated. Do not search the source document,
highlight query terms, or derive a new score. Use the same bounded projection
for Evidence display labels, while retaining the Evidence contract's own
already bounded excerpt.

`documentLabel` prefers the exact sanitized S-028 `display_filename` reached by
verified lineage. For pre-S-028 or unavailable registrations, use a stable safe
label such as `Document doc_ab12cd34`; do not infer a filename from Artifact
summary, storage locator, metadata path, or question text. The full document ID
remains in diagnostics.

Format locator labels from an allowlist of typed fields and schemas, for
example page and bounding box, heading path, paragraph/line, slide/shape,
sheet/cell range, or table/cell. Unknown valid locator schemas receive a short
schema label and keep their structured value only in expanded diagnostics.
Never stringify locator JSON into the primary table or interpolate untrusted
HTML.

### Server-Owned Decision Path

Keep `candidates[]` unchanged in meaning and independently selectable. Add a
separate `decisionPath` projection with ordered stage columns and rows. Each row
is keyed by exact `(documentId, chunkId)` and may contain:

- per-retriever rank, safe score, and score kind;
- fusion rank/score and preserved contributor ranks;
- rerank input/output rank, safe score, and returned decision reason;
- context source rank/score, selected/excluded state, and returned rationale;
- the safe document label, bounded excerpt, and friendly locator.

Columns follow the resolved plan/Trace order. Rows follow the first exact
appearance in those ordered candidate sets, with the stable identity as the
tie-breaker; context-only identities follow in returned context-decision order.
Missing stage participation is explicit `NOT_PRESENT`, not rank zero. Conflicting
document identity for the same Chunk ID, an unbound index, or a decision that
cannot be matched remains visible as bounded `UNRESOLVED` diagnostic data and
is never attached to another row.

This projection is a read model only. It performs no retrieval, fusion,
reranking, threshold evaluation, score normalization, context selection, or
reordering of a source candidate set. The browser renders it verbatim and does
not reconstruct the matrix.

### Stage Trace And Duration

Return `durationMs` for every attempt using the same workbench rule already in
`diagnosis.py`: `max(0, int((ended_at - started_at).total_seconds() * 1000))`
when both timestamps exist, otherwise `null`. The primary stage table contains
stage, attempt, state, Plugin, actual duration, and safe failure. Start/end,
input/output Artifact identity, metrics, and quality signals stay available in
an expandable attempt detail rather than consuming the narrow table.

No metric duration substitutes for wall time, and no running duration is
estimated in the browser.

### Evidence Actions And Progressive Detail

Render each Evidence item as an unframed ruled row with this hierarchy:

```text
citation key | document label | context state
bounded excerpt
friendly locator | contributors summary | decision rationale
[source preview]
<details> document/chunk IDs, structured locator, scores, hierarchy/table IDs
```

There are two independent command contracts:

- **Validated answer citation:** appears only inside a citation-valid
  `ANSWERED` result and only for keys in `final.citationKeys`. It opens the
  source through the matching Evidence item.
- **Evidence source preview:** appears on any Evidence row with a
  lineage-verified `sourceArtifactId` and exact `sourceLocator`, including
  clarification, abstention, verification failure, and repair exhaustion. Its
  label and accessible name say source preview, not citation.

When source identity or locator is absent, show `源预览不可用` as non-action
text. Both valid commands call the unchanged
`inspector(id, origin, selectedLocator)`. S-024 continues to own conditional
tabs, locator selection, drawer focus trap, inert background, Escape, scroll
lock, and focus return. Preserve the Query URL, requested Run, S-027 diagnosis
parameters, candidate tab, and expanded Evidence state while the drawer opens.

### Final State And Verification/Repair Trace

The result band always displays exactly one authority from `final.state`:

- `ANSWERED`: validated answer text and validated citation actions;
- `CLARIFICATION_REQUIRED`: returned safe action, no answer/citation actions;
- `ABSTAINED`: returned safe action and shortage diagnostics, no answer;
- `FAILED`: returned safe action or bounded unavailable copy, no answer.

Verification results and repeated repair attempts are an ordered, collapsed-by-
default Trace section using returned stage attempt order and typed detail. A
repair success still ends as `ANSWERED`; verification failure or exhausted
repair ends as `FAILED`. `VERIFY_FAILED` and `REPAIRING` are never product final
states or status filters.

### Delivered Presentation Baseline (Superseded For This Repair)

Retain the native-DOM shell and flat UI-013 language. At 1440 px use tracks near
`minmax(300px, .95fr) minmax(500px, 1.35fr) minmax(280px, .8fr)` so controls and
the decision path gain width while the answer remains readable. The candidate
tabs remain the authoritative raw-stage view; the decision path is a separate
dense table below them. Evidence details are collapsed by default.

Below 900 px preserve the current order `control -> retrieval -> answer` and
full-width stacking. Tables own labelled horizontal scroll; the document does
not. The S-024 Inspector remains full-width at 644 px. Do not scale font size
with viewport width, create nested cards, or import prototype scenario/preset
controls.

### Loading, Failure, And Accessibility

- Preserve the existing request-generation guards for option, preflight,
  submit, and poll races. A newer input or request invalidates all older UI
  authority and disclosure acknowledgement.
- Keep persistent `role=status` regions for loading/polling and scoped
  `role=alert` failures. Preserve the last valid Run projection on transient
  polling failure and offer only the authority-valid retry.
- Candidate, decision-path, Context, Evidence, Trace, and source-registration
  absence each have distinct empty/unavailable states. Do not render raw
  `null`, `{}`, `[]`, or JSON as the primary UI.
- Candidate tabs retain native tab semantics and roving keyboard focus.
  Expanders use native `<details>/<summary>`. Status and decision meaning use
  text/icons as well as color; all controls retain visible focus.

## Workspace And Information-Density Repair

### Desktop Viewport And Pane Ownership

At widths of 900 px and above, copy only the structural lesson from the current
Registry implementation:

```text
.shell-body:has(.query-page)  100dvh, rows: shell header / minmax(0, 1fr)
.query-page                   rows: page title / minmax(0, 1fr)
.query-workspace              min-height: 0, overflow: hidden
  control pane                min-height: 0, overflow-y: auto
  retrieval pane              min-height: 0, overflow-y: auto
  answer pane                 min-height: 0, overflow-y: auto
```

Use `minmax(0, 28fr) minmax(0, 40fr) minmax(0, 32fr)` as the desktop tracks.
The zero minimum is intentional: exact 900 px containment takes precedence over
an arbitrary pane minimum, and any dense table owns its labelled horizontal
scroll. Give every pane `overscroll-behavior: contain` and a stable vertical
scrollbar gutter where supported. A pane scroll must not move either sibling
pane or the page title. Do not add Registry-style horizontal scroll buttons or
its 1420/1300 px table minimums; Query tables target approximately 560-680 px
minimum widths and scroll only inside their labelled region when necessary.

Remove the shared 12 px blanket padding from the retrieval and answer panes.
Use 8-12 px padding inside ruled headers, command bands, result bands, and
Evidence entries so the columns read as one flat workbench rather than three
large padded cards. The control pane may retain compact internal padding.

Below 900 px, disable viewport locking and pane-local vertical scroll. Preserve
normal document scrolling and the existing order `control -> retrieval ->
answer`; each pane becomes full width, pane separators become horizontal, and
tables retain local horizontal scroll. The S-024 Inspector remains full-width
at 644 px with its existing focus trap, locator synchronization, and scroll
lock. No fixed/sticky child may cover a control or Evidence entry.

### Compact Explicit Query Command

Keep the existing two-authority execution sequence explicit. The command area
has these states:

1. Initial, invalidated, or retryable input: question (three compact rows),
   Query Profile, one indexed Artifact selector, and the red primary
   `预检并准备运行` command.
2. Resolved local plan: compact resolved-plan summary and the red primary
   `创建 Query Run` command. This remains a second explicit action; preflight
   never auto-submits.
3. Resolved external plan: the returned external stages, warning treatment,
   acknowledgement checkbox, and disabled-until-acknowledged create command are
   visible together. Do not collapse or obscure this boundary before submit.
4. Active Run: replace create authority with the returned owner-authoritative
   `停止` command and an in-progress status. Terminal/no-owner states expose no
   Stop command.

Use one primary red command for the current step, with the existing Lucide play
or stop icon where available; do not show two competing primary actions. Keep
the persistent live status compact, but retain `role=status` and promote a
scoped failure to `role=alert`. Input changes still invalidate the preflight,
acknowledgement, pending submit, previous projection, and Stop authority exactly
as today.

The full plan digest is diagnostic identity, not primary copy. Place it in a
native details disclosure with full stage/attempt Artifact identities. Keep the
resolved plan visible as a dense, border-separated list in the control pane:

```text
state icon | stage key
             Plugin                          duration
```

Before Run creation, source rows from returned preflight stages and show no
invented duration/state. After Run creation or on a requested-Run deep link,
replace them with returned ordered `stages[]`, status, Plugin, and `durationMs`.
The browser must not merge stale preflight rows into a different Run. Attempt,
input/output Artifact, metrics, quality, and safe failure details remain in
collapsed native details directly below the compact list.

### Retriever Candidates And Authoritative Decision Table

Partition `candidates[]` only for presentation using the returned Artifact type:

- `retrieval.candidate.set` items become tabs in server order. Each tab label is
  its returned `stageId` plus `rows.length`; unavailable sets remain explicit
  zero-count/unavailable tabs when their typed Artifact identity is present.
- `fusion.candidate.set` and `rerank.candidate.set` never become tabs. Their
  rows are already represented, with their independent stage columns, in the
  server-owned `decisionPath`.
- Missing or unknown Artifact type is not guessed from a stage name. It stays
  out of Retriever tabs and receives a bounded unavailable diagnostic; the
  decision table still renders any returned path facts.

This is a presentation grouping, not a loss of stage provenance. Do not mutate
`candidates[]`, synthesize a candidate set, or construct a path from tab DOM.
The raw Retriever table uses `Rank`, `Document / Chunk`, `Excerpt`, `Score`, and
`Locator`. Use returned labels/excerpts and a shortened visible Chunk identity
with the full identity in accessible title or row details. A Retriever row does
not repeat fusion contributions or rerank decisions.

Render `decisionPath` immediately below the Retriever tabs as one ruled table.
Columns follow `decisionPath.columns` and classify their display using the
matching returned candidate Artifact type: Retriever rank, fusion rank/score,
rerank rank/score/returned decision, and context rank/score/returned rationale.
Rows follow `decisionPath.rows` exactly. `NOT_PRESENT`, unresolved identities,
selected context decisions, and candidate-only dropped decisions remain
explicit text states. The browser may format returned numbers and labels but
must not join by Chunk ID, calculate a score, infer a threshold, decide
selection, or reorder rows.

Move Context Shortage to a compact status band below the decision table. Show
reason and selected/minimum items/tokens on one or two lines; retain any extended
facts in details. The ordered Trace table and attempt details no longer consume
the retrieval pane because their compact authoritative summary is in the
control pane.

### Answer, Verification, Citations, And Evidence

Use the reference's answer-to-proof reading order:

1. A ruled header contains `答案` and the exact final-state tag on one line.
2. The returned validated answer or safe action follows. Only `ANSWERED` may
   render answer text.
3. Validated citation commands render as `citation key · friendly locator` and
   invoke the already matched Evidence source. They remain absent for every
   non-answered state.
4. A compact, always-visible Verification band shows the latest returned
   outcome and the number of returned verification attempts. Absence is stated
   as unavailable; no result is inferred from the final state. Ordered failure
   codes, missing keys, and repair attempts remain in collapsed details.
5. `Evidence · EvidenceSet/v1` follows immediately, as repeated 1 px bordered,
   zero-radius diagnostic entries rather than one long definition surface.

Each Evidence entry shows citation key, safe document label, returned context
status/reason, excerpt, friendly locator, compact contributor summary, inclusion
rationale, and the distinct source-preview command before technical details.
Keep Document/Chunk UUIDs, structured locator, score detail, hierarchy, and
table element IDs inside the existing native details. Long text wraps; identities
either truncate with an accessible full value or wrap only inside details.

The Evidence host iterates only `x.evidence`, which is already the validated
EvidenceSet projection. A `decisionPath` row whose Context reason is excluded,
dropped, `NOT_PRESENT`, or unresolved is diagnosis only and must never be
copied into `.evidence-row`, assigned a citation key, or offered as source
Evidence. An Evidence item may still be shown for non-answered states when the
server returns it; that does not create answer support. Its source-preview
availability continues to depend only on verified source Artifact and locator.

### Fixture And Visual Evidence

Retain the seven scenarios and fourteen reviewed viewport combinations. Replace
visible route tokens with exact natural Simplified-Chinese questions through a
test-only `scenario -> question` map; the fixture preflight maps those exact
questions back to scenario state. Do not add scenario query parameters,
production presets, hidden production controls, or product logic that parses
test tokens.

Upgrade the fixture to the same production response shape, including candidate
`artifact.artifactType`. The factual/table cases include at least keyword and
vector Retriever sets with multiple plausible Chunk candidates, then returned
fusion/rerank/context path rows that contain both selected and dropped results.
Each scenario keeps contract-valid Chinese filenames, excerpts, typed locators,
Evidence, final state, and Verification detail. The hierarchy case retains
multiple complementary Evidence; the table case retains an exact sheet/cell
locator and synchronized Inspector content.

Refresh, do not expand, the fourteen 1440/644 PNG baselines. Add DOM/geometry
tests at 1280 x 900 and exactly 900 x 900; these are not new goldens. At 1440,
the compact plan, active Retriever candidate surface, answer/final status, and
first Evidence entry must all intersect the first viewport simultaneously. At
1440/1280/900 the workbench remains within the available shell height, tracks
stay within a reasonable tolerance of 28/40/32, each pane owns vertical scroll,
and scrolling one overflowing pane leaves sibling `scrollTop` and title geometry
unchanged. At 644, assert normal document scrolling and stacked pane order.

## Relevant Impacts

- **UI:** Refactor only the Query Lab render helpers and Query-specific styles.
  Preserve the workbench shell, local Archivo/Lucide assets, shared primitives,
  S-024 Inspector implementation/selectors, and S-027 route helpers.
- **API/read model:** No change. Consume the delivered
  `workbench-query-run/v1` fields without browser recomputation; endpoint paths
  and response semantics remain unchanged.
- **Repository/data:** No change. The delivered exact bounded S-028 metadata
  lookup remains the only document-label source; no write path, table,
  migration, Artifact contract, or Run schema changes.
- **Security:** Source labels come only from S-028-sanitized metadata after
  verified lineage. Excerpts and locator labels are bounded and text-node
  rendered. Raw vectors, storage paths, prompts, credentials, endpoints,
  provider bodies, arbitrary metadata, and unsafe exceptions remain excluded.
- **Compatibility:** Preserve one Search Artifact per Query Run, final-response
  validation, async authority, external disclosure, owner-only Stop,
  `inspector(id, origin, selectedLocator)`, and requested Run/diagnosis URL
  context. Older source artifacts work with safe fallback labels.

## Deterministic Visual Contract

Retain the fourteen contract-valid scenario captures and the exact S-022
capture conditions and RGBA comparison policy. Refresh the image bytes and
manifest hashes only after reviewed workspace recomposition; do not add more
goldens. The manifest continues to contain:

| File stem (both `-1440.png` and `-644.png`) | Scenario | Required visible evidence |
|---|---|---|
| `query-fact-answered` | high-precision fact, `ANSWERED` | Retriever-only tabs with counts, multiple Chinese candidates, selected/dropped decision rows, validated citation with locator, compact plan and duration |
| `query-table-answered-inspector` | table-cell answer with Inspector open | table/cell locator, table Evidence, distinct source-preview command, synchronized S-024 table/source selection |
| `query-hierarchy-answered` | hierarchical multi-Evidence answer | parent/child Evidence, multiple contributors/citations, inclusion rationale, progressive technical detail |
| `query-clarification-required` | ambiguous question | clarification action, diagnostic Evidence source preview, no answer or answer citation |
| `query-abstained` | unanswerable/shortage | excluded decision path, shortage facts, Evidence preview where lineage exists, no answer |
| `query-repair-answered` | initial verification failure then bounded repair success | authoritative `ANSWERED`, ordered verification/repair detail, unchanged Evidence identity |
| `query-repair-exhausted` | verification failure and exhausted repair | authoritative `FAILED`, failure codes and attempts, Evidence source preview, no answer/citation |

This remains fourteen main goldens. The open Inspector scenario at both widths is
part of the table case rather than a decorative separate fixture. Use real
typed locator shapes, natural Chinese questions, distinct excerpts, sanitized
filenames, multiple Retriever sets and candidates, selected/dropped decisions,
and deterministic timestamps/scores. Do not expose scenario tokens in visible
inputs or use prototype IDs, scores, provider names, or scenario controls as
production data.

Loading, empty options, external acknowledgement, active Stop, polling failure,
tab keyboard navigation, collapsed/expanded details, unavailable legacy label,
and source-preview focus return are DOM/interaction assertions rather than more
goldens. Capture tests assert exact viewport and font prerequisites,
`documentElement.scrollWidth <= innerWidth`, stable desktop tracks/narrow order,
positive target sizes, pane-local vertical scroll, sibling-scroll independence,
labelled table overflow, no overlap, first-view hierarchy, and selected source
locator visibility. Dedicated non-golden 1280/900 tests protect the responsive
boundary without increasing baseline maintenance.

The manifest keeps Story/UI anchors, prototype SHA-256, fixture revision,
browser/runtime/media/font/readiness conditions, and every baseline SHA-256.
Tests never create or update reviewed baselines. Failed comparisons may write
current/diff PNGs only under the test temp directory.

## Alternatives And Risks

- Reading the pinned index in the browser was rejected because it would expose
  vectors and duplicate identity/validation logic. The server projection reads
  typed artifacts and returns only bounded display facts.
- Building the decision path from DOM candidate tabs was rejected because the
  UI could silently misjoin duplicate Chunk IDs or recompute semantics. The
  server owns the exact `(documentId, chunkId)` join.
- Replacing independent candidate sets with one matrix was rejected because it
  erases stage provenance. The decision path is additive, not a replacement.
- Paging the document catalog or inferring filenames from storage/summary was
  rejected. Exact source-ID lookup plus a stable generic fallback preserves
  S-028's safety boundary and old Artifact compatibility.
- Returning source preview only for supported answers was rejected because it
  prevents diagnosis. Preview availability proves source identity, while an
  answer citation separately proves final validation.
- A larger frontend framework or copied prototype markup would fork the current
  shell and interaction model for no architectural benefit.
- More joins increase Run projection cost. Bound all Artifact/lineage/document
  lookups, parse the index once, batch registration reads, and degrade individual
  display facts to unavailable without hiding the authoritative Run result.
- Keeping document-level scrolling on desktop was rejected because it prevents
  simultaneous control, decision, and answer inspection. Viewport containment
  plus pane-local scroll matches the workbench task and the proven Registry
  structure.
- Copying Registry's 1420/1300 px table and horizontal scroll buttons was
  rejected because Query diagnosis needs a narrower, continuously scannable
  middle pane. Only its viewport, `minmax(0, 1fr)`, overflow, and drawer lessons
  are reused.
- Keeping fusion/rerank as candidate tabs was rejected because it duplicates
  the same progression shown by `decisionPath`. Retriever sets remain
  independently tabbed; downstream stage provenance remains independently
  visible as returned decision-table columns.
- There is a compatibility risk if a test fixture omits the production
  candidate Artifact descriptor. Correct the fixture to the production response
  shape rather than guessing a stage kind from its name in browser code.
- A requested-Run deep link has no live preflight object. Its left plan list
  must therefore use returned `stages[]`; never retain or synthesize an earlier
  preflight disclosure for another Run.

## Explicit Exclusions

- Multiple Search Artifact selection or execution. S-011 and the engine bind
  exactly one immutable Search Artifact; changing that requires product/core
  design and contract work.
- Prototype question presets, scenario controls, synthetic fixtures in product
  UI, or a direct-run button that bypasses preflight/disclosure.
- Browser retrieval, fusion, reranking, scoring, thresholding, context selection,
  verification, or decision-path reconstruction.
- Raw vector display or serialization, storage-path-derived labels, and unsafe
  provider/Artifact payload exposure.
- `VERIFY_FAILED` or `REPAIRING` as product final states.

## Test Strategy

- Keep the existing Query workbench unit/API/repository tests unchanged except
  for any response-shape assertion directly affected by fixture realism. They
  remain the regression gate for exact joins, bounded display data, final
  validation, authority, safe failure, lineage, and vector non-disclosure.
- Update the fixture with a test-only natural-Chinese-question scenario map,
  production-shaped candidate Artifact descriptors, at least keyword/vector
  Retriever sets, multiple candidate rows, and selected/dropped decision paths.
  Assert the visible textarea contains the natural question and no scenario
  token after execution.
- Update `test_s025_query_options_stale_preflight_poll_stop_and_terminal_cleanup`
  for compact current-step commands while retaining every authority and stale-
  response assertion. Add explicit checks that external disclosure,
  acknowledgement, and blocked create command remain visible before execution.
- Update `test_s025_query_final_state_visual_matrix` to assert Retriever-only
  tabs and counts, absence of fusion/rerank tabs, verbatim downstream decision
  cells, visible Verification summary, citation key plus locator, selected and
  dropped rows, and the rule that dropped candidate identity never appears in
  `.evidence-row`. Retain all seven states at 1440/644 and the Inspector table
  synchronization path.
- Add a focused desktop geometry test parameterized at 1280 and 900 px. Together
  with 1440 visual assertions, verify 100dvh containment, approximately
  28/40/32 tracks, `overflow-y:auto` on all panes, genuine independent scrolling,
  scoped horizontal table overflow, stable title geometry, positive control
  sizes, and no document horizontal overflow. Retain 644 stacked-order and
  normal document-scroll assertions.
- Continue the non-answered source-preview/focus/Escape/URL-context test and
  S-024 Inspector, S-027 route-context, S-022 shell, S-028 document safety, and
  broader non-Docker workbench regressions. Capture and compare exactly the
  fourteen refreshed goldens under the pinned manifest environment.

## Implementation Checklist

- [ ] Recompose Query DOM into compact control/plan, Retriever/decision, and
  answer/verification/Evidence bands without changing endpoint or read-model
  contracts.
- [ ] Add Query-scoped 100dvh containment, 28/40/32 desktop tracks, pane-local
  scrolling, compact ruled spacing, and below-900 normal stacked flow; do not
  import Registry's wide-table minimum or scroll buttons.
- [ ] Keep preflight and external acknowledgement explicit; implement one red
  current-step command, compact live status, owner-authoritative Stop, and
  requested-Run stage-list fallback.
- [ ] Filter tabs by returned `retrieval.candidate.set`, add counts and the
  compact raw table, and render fusion/rerank/context only from `decisionPath`.
- [ ] Reorder answer/status/citation/verification/Evidence, include locator in
  citation commands, and keep dropped candidates out of Evidence.
- [ ] Upgrade only the test fixture and browser/visual assertions, refresh the
  same fourteen goldens, and add 1280/900 non-golden geometry coverage.
- [ ] Run focused, visual, Inspector, route-context, document-safety, and broad
  non-Docker workbench regressions; record any environment-only residual.

## Open Questions

None. The authorized Story Pipeline may proceed directly to development.

## Approval

Approved by the user's 2026-09-15 instruction to execute the recommended S-025
workspace/information-density repair after synchronizing with `main@aa584cc`.
This revision changes only Query Lab presentation, styles, fixtures, and tests;
it introduces no product, engine, API, repository, durable schema, migration,
security, or external-call decision requiring separate approval.

## Change History

- **2026-09-13:** Created the initial just-in-time design and delivered the
  API-backed S-025 workflow.
- **2026-09-14:** Revised for the first UI-reference parity repair and delivered
  the three-pane Query Lab with eight final-state baselines.
- **2026-09-14:** Re-evaluated `main@6118e85` after S-028 and approved this
  bounded diagnostic-parity repair: safe candidate/source display facts,
  server-owned decision path, separated citation/source actions, actual stage
  duration, progressive Evidence, rebalanced panes, and realistic visual cases.
- **2026-09-15:** Re-evaluated `main@aa584cc` and approved the bounded
  workspace/information-density repair: viewport-bound desktop panes, compact
  explicit execution authority, left-side plan, Retriever-only tabs,
  authoritative combined decision table, reference-ordered answer/Evidence,
  natural Chinese fixtures, retained fourteen goldens, and 1280/900 geometry
  coverage. The delivered provenance/read projection remains unchanged.
