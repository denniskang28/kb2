# Story Design: S-028 - Persisted Document List

## Status

Approved for Story Pipeline implementation.

## Story Contract Snapshot

- Story: `S-028`, confirmed 2026-09-14.
- Design basis: the confirmed S-028 contract, S-024's delivered document
  preflight/Run/Artifact behavior, current trace persistence and workbench code,
  UI-003 (`isDocs`), UI-005 (`artOpen`), and UI-013.
- Delivery boundary: add a durable catalog for newly confirmed document
  submissions, a safe paged projection, and the populated/exceptional Documents
  page states. Preserve S-024 preflight, immutable Run recovery, and Artifact
  inspector contracts.
- Material decisions requiring approval: None. The Story Pipeline invocation
  authorizes the choices recorded below. No product-scope or external-provider
  behavior changes.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Persist one `document_submissions` row in the same transaction that publishes the `ingestion.source` Artifact. Preflight remains process-local and cannot write the table. The listing is reconstructed from PostgreSQL after restart. | Contract tests prove preflight creates no record and each confirmed submission registers once; PostgreSQL integration creates a submission, reconnects, and reads the same row. |
| 2 | The repository joins the catalog row to its source Artifact, owning ingestion Run, and frozen `ingestion_run_evidence`. A typed service projection returns source ID, safe display filename, media/format facts, byte size, optional document class, selected Profile, Run identity, authoritative Run state, and eligible Artifact actions. Missing optional values are `null`. | Projection tests assert every field comes from stored facts and `documentClass: null` remains unavailable; browser tests assert explicit `不可用` rendering. |
| 3 | Every source Artifact is the stable document identity, so repeated filename/digest submissions remain separate. Rows sort by `(registered_at DESC, source_artifact_id DESC)` and use that tuple as a keyset cursor. State is read from the owning Run on every list request. | Repository/integration tests cover equal filename/digest rows, tie-break ordering, state transition after refresh, and no merging. |
| 4 | Each row renders an enabled Run link only when `latestRun` exists, an inspect-source icon only when `actions.sourceArtifactId` exists, and an inspect-output icon only when `actions.outputArtifactId` exists. Both Artifact controls call the existing global `inspector(...)`; no start/query/delete/lifecycle control is added. | API and DOM assertions cover present/absent action combinations, exact Run URL, inspector IDs, accessible labels/tooltips, and absence of destructive controls. |
| 5 | `GET /api/workbench/documents` implements bounded keyset paging. Initial load and Refresh reset the cursor; Load more appends exactly once behind a request-generation guard. Loading, empty, populated, and recoverable error are explicit list-region states while the header upload command remains mounted. | Contract tests cover cursor validation, bounds, page boundaries, and failed reads; browser tests cover retry, stale-response suppression, append de-duplication, and upload availability in every state. |
| 6 | A dedicated response model uses `extra="forbid"` and emits only bounded catalog/trace facts and permitted Artifact IDs. Repository rows may contain neither Artifact storage locator nor content. API errors use the existing safe problem envelope. | Contract/source tests assert the exact response key set, length bounds, absent digest/content/path/provider fields, and no raw manifest serialization. |
| 7 | Replace S-024's current-submission placeholder with the UI-003 dense ruled table and page-local paging footer. At widths below 900 px, a `.document-table-wrap` owns horizontal overflow while the page and shell do not; the title commands wrap and remain reachable. | Exact 1440 x 900 and 644 x 900 browser geometry assertions cover table density, command visibility, scoped overflow, focusable actions, and zero page-level overlap. |
| 8 | Extend the deterministic Chrome visual harness and add reviewed S-028 baselines for populated, empty, loading, and recoverable-error states at both viewports. Fixtures use obviously non-production values and exercise action eligibility. | Eight RGBA baseline comparisons plus manifest provenance and state-specific semantic assertions. |

## Current Code Findings

- `DocumentWorkbenchService` supports process-local preflight tokens, confirmed
  Run creation, ingestion Run projection, rerun preflight, and the shared
  Artifact inspector. It has no document listing method or catalog reader.
- A confirmed submission persists an `opaque.bytes/v1` Artifact under the
  `ingestion.source` attempt. Its manifest safely stores identity, size, type,
  producer, and digest, but its fixed summary is not a filename and must not be
  parsed as one.
- Frozen `ingestion_run_evidence` already owns media type, extension, byte size,
  document class, selected Profile, and resolution tier. The persisted Run owns
  processing state. The original filename is not currently persisted in any
  structured field, so S-028 cannot be implemented truthfully without a narrow
  durable data addition.
- `TraceRepository.list_artifact_manifests()` sorts UUIDs rather than creation
  time and filters by schema only. It neither identifies source submissions nor
  supports stable paging, so it is not an appropriate list basis.
- S-024's Documents page currently shows only an honest empty/current-preflight
  panel. The upload modal and source/Run Artifact inspector are already usable
  and must remain unchanged apart from refreshing the list after a successful
  submission when navigation does not immediately leave the route.
- The shared shell already provides UI-013 tokens, semantic status tags,
  accessible icon buttons, page-level overflow protection, and a below-900 px
  breakpoint. Existing S-022/S-024 visual infrastructure pins local Archivo,
  Lucide provenance, Chrome flags, RGBA comparison, and viewport geometry.

## Proposed Approach

### Durable Submission Registration

Add Alembic revision `0006_document_submissions` after the current `0005`
head. It creates:

```text
document_submissions
  source_artifact_id uuid primary key references artifacts(id) on delete restrict
  run_id             uuid not null unique references runs(id) on delete restrict
  display_filename   varchar(255) not null
  media_type         varchar(128) not null
  registered_at      timestamptz not null default current_timestamp
```

Add the descending keyset index
`(registered_at DESC, source_artifact_id DESC)`. The source Artifact ID is the
document identity; neither filename nor digest is unique. The owning Run is
unique because the current engine creates exactly one source Artifact for each
ingestion Run. No content, storage locator, filesystem path, credential,
mutable status, or copied Profile document is stored in this table.

Extend `SourceSubmission` with required bounded `filename` and `media_type`
fields. Validate filename as a single display leaf: non-empty after whitespace
normalization, no control characters or `/`/`\\` path separators, maximum 255
characters. Apply the existing sensitive-metadata detector before persistence;
a suspicious name is persisted as `[redacted]`, while media type and extension
remain available from frozen resolver observables. Media type is a normalized,
bounded MIME value and never a provider payload. Update all internal engine
callers and fixtures to provide these fields; this is an internal typed contract
change, not a new HTTP upload shape.

The source-publication path gains a typed `DocumentSubmissionInput` rather than
encoding metadata into `ArtifactInput.summary`. `IngestionEngine` passes it only
when materializing `ingestion.source`. `ArtifactService.complete_with_outputs`
and `TraceRepository.complete_outputs` accept that optional registration and
validate that it accompanies exactly one `opaque.bytes/v1` output produced by
the matching ingestion Run/source attempt. The repository inserts the Artifact,
stage output, and catalog row in its existing explicit transaction before
committing. Any catalog constraint or validation failure rolls back Artifact
publication and records the existing bounded trace-storage failure; there is no
half-registered document.

The migration intentionally does not synthesize filenames for old Artifacts.
Pre-S-028 sources remain accessible through their Runs but are not catalog rows,
because deriving names from summaries, IDs, or storage paths would violate the
Story. Rollout requires only `alembic upgrade head`; no destructive backfill or
feature flag is needed. Downgrade drops only the catalog table and index, never
Artifacts, Runs, or stored bytes.

### Repository Query And Projection

Add `TraceRepository.list_document_submissions(limit, cursor)` returning a
bounded typed tuple plus a next-position value. One SQL query selects `limit +
1` rows and joins only:

- `document_submissions` for source identity, filename, media type, and time;
- `artifacts` for source byte size/schema;
- `runs` for current authoritative state and timestamps;
- `ingestion_run_evidence` for selected Profile and optional observables;
- one lateral eligible-output selection for a non-source Artifact whose
  producing attempt is still `SUCCEEDED`/`SUCCEEDED`, ordered by Artifact
  `created_at DESC, id DESC`.

The query requires an ingestion Run, the exact `ingestion.source` successful
attempt/output relationship, and the directory's matching source and Run IDs.
This prevents unrelated opaque Artifacts from entering the catalog. The source
action is advertised because the registered source relationship is valid; the
output action is optional and uses the deterministic lateral result. The v1
`latestRun` is the explicitly registered owning Run. A future source-reuse
feature must add explicit persisted lineage before it may select another Run;
filename or digest matching is never a relationship.

Cursor order is `(registered_at DESC, source_artifact_id DESC)`. A URL-safe
base64 cursor encodes version `1`, the last UTC timestamp, and UUID; parsing is
strict, capped at 256 characters, and invalid cursors return
`DOCUMENT_CURSOR_INVALID` with 422. The predicate is tuple-less for portable
clarity: `registered_at < ts OR (registered_at = ts AND source_artifact_id <
id)`. Default `limit` is 25, accepted range is 1 through 50, and `nextCursor`
is `null` when no extra row exists. Inserts during traversal may appear only on
a fresh first page; existing page traversal has no duplicates or omissions.

`DocumentWorkbenchService.documents_page()` converts repository records to
strict Pydantic workbench contracts. It never opens Artifact content. Optional
`documentClass`, `format`, and output action remain `null` rather than inferred;
`format` is the persisted resolver extension when present, otherwise `null`
even if a MIME suffix looks suggestive. Run state is copied directly from
`runs.state` on each request.

### List API

Add:

```http
GET /api/workbench/documents?limit=25&cursor=<opaque>
```

with response shape:

```json
{
  "contractVersion": "workbench-document-list/v1",
  "items": [{
    "sourceArtifactId": "uuid",
    "filename": "sample.pdf",
    "mediaType": "application/pdf",
    "format": "pdf",
    "byteSize": 1234,
    "documentClass": null,
    "profileId": "native-long",
    "registeredAt": "2026-09-14T08:00:00Z",
    "latestRun": {"id": "uuid", "state": "RUNNING"},
    "actions": {
      "sourceArtifactId": "uuid",
      "outputArtifactId": null
    }
  }],
  "page": {"limit": 25, "nextCursor": null}
}
```

Allowed Run states are exactly `PENDING`, `RUNNING`, `SUCCEEDED`, and `FAILED`;
the UI maps these server values to localized labels but does not combine or
reinterpret them. `filename`, `mediaType`, `format`, `documentClass`, and
`profileId` have explicit response bounds. The endpoint catches repository or
projection failures as `DOCUMENT_LIST_UNAVAILABLE`/503 and uses the existing
`workbench-problem/v1` envelope. It never includes content/content digest,
plan/configuration data, resolution rules, errors, provider data, parent IDs,
or `ArtifactManifest.storage_locator`.

### Client State And Actions

Keep the dependency-free DOM implementation. `documents()` owns a small list
state object: `{generation, items, nextCursor, mode}`. On initial load and
Refresh it increments `generation`, clears cursor/items, leaves the title and
upload command mounted, and renders skeleton table rows. Load more retains the
current rows, disables its control, and requests `nextCursor`. Responses whose
generation is stale are ignored. Source IDs are the de-duplication assertion;
receiving the same ID twice in one traversal is treated as a recoverable list
error rather than silently merging it.

The state DOM is:

```text
main.documents-page
  header.title-row.documents-title
    title + purpose
    div.documents-commands
      button Refresh [refresh icon]
      button Upload [upload icon]
  section.documents-surface[aria-labelledby][aria-busy]
    div.document-table-wrap
      table.document-table
    div.document-list-loading | div.empty-state | div.notice-failure
    footer.document-page-actions
```

The populated table uses columns `文档`, `格式`, `处理类别`, `Ingestion
Profile`, `最近 Run`, `状态`, and `操作`. The first cell shows the safe filename,
byte size, and a wrapping monospace source ID. `format` prefers the returned
extension, otherwise shows the media type; this is a presentation fallback
between two server-owned facts, not state inference. Optional fields render
`不可用`. Status uses the existing semantic mappings: success, info, failure,
and neutral for pending. There is no synthetic `NOT_INGESTED` state.

Run is an ordinary link to
`/workbench/runs?run=<id>&legacy=ingestion` using the existing URL helper.
Artifact actions are 30 x 30 Lucide icon buttons with visible focus treatment,
`title`, and precise `aria-label` (`检查 Source Artifact` / `检查最新输出
Artifact`). They call the existing `inspector(id, event.currentTarget)` so modal
focus and return behavior remain S-024-owned. Unsupported controls are omitted,
not disabled. No pictured start-ingestion or query action is copied from the
prototype.

Initial empty copy distinguishes the absence of persisted submissions from
preflight. A 503 renders a stable inline failure notice with `重试` while
retaining Refresh and Upload. Load-more failure keeps already rendered rows and
shows a footer-scoped error/retry; it does not replace the list. Completing an
upload continues the current redirect to the Run page, so the next Documents
navigation naturally reloads the catalog. Preflight-only file selection and
failed confirmation never alter list state.

### Responsive And Visual Design

At 1440 x 900, `.document-table` spans the content area with ruled header/body,
43-52 px compact rows, a minimum width near 940 px, fixed-size action controls,
and wrapping only in identity cells. The title row places Refresh and the
accent Upload command at the right. No document card grid is introduced.

Below 900 px, the title row and command group wrap without hiding either
command. `.document-table-wrap` gets `overflow-x:auto`, `overscroll-behavior-x:
contain`, a keyboard-focusable labelled region, and the table retains its
minimum width. The wrapper, not `html`, `body`, shell, or title row, is the sole
horizontal scroller. At 644 x 900 all buttons remain at least 30 px, identity
text wraps within its column, status/action cells remain stable, paging is
below the scroller, and opening the existing inspector still fits the viewport.

Add `tests/visual/baselines/s028/manifest.json` and eight reviewed images:
`documents-{populated,empty,loading,error}-{1440,644}.png`. The fixture server
returns unmistakable test identities, uses a delayed response for a capturable
loading state, and a safe 503 for error. Captures retain the S-022 deterministic
font/media/locale/Chrome setup and non-mutating RGBA comparison. Geometry checks
assert `document.documentElement.scrollWidth <= innerWidth`; at 644 px the
table wrapper must have `scrollWidth > clientWidth`, while at desktop it must
fit without forced page overflow.

## Relevant Impacts

- **Data and migration:** one additive catalog table and keyset index. Existing
  Runs/Artifacts are unchanged; no synthetic backfill.
- **API compatibility:** one additive GET endpoint and internal typed source
  metadata fields. Existing preflight, submission receipt, Run, rerun, and
  Artifact endpoints remain byte-for-byte compatible.
- **Security:** leaf-name validation/redaction occurs before persistence; list
  queries and contracts exclude raw bytes, digests, storage locators, paths,
  configuration, provider payloads, and errors. Cursor input is bounded and
  parameterized.
- **Observability:** normal list failures reuse the safe problem code; no raw
  database exception is sent to the browser. Existing Run/trace records remain
  the operational diagnostic owner.
- **Rollout:** migrate before serving the new endpoint. An empty post-migration
  catalog is a valid first-use state, not a migration failure.

## Alternatives And Risks

- Reusing Artifact `summary` for filename was rejected because it is an
  unstructured diagnostic field and existing sources contain a fixed summary.
- Storing metadata only after `IngestionEngine.submit()` returns was rejected:
  it creates a crash window where a source Artifact exists without its document
  record and cannot represent RUNNING submissions.
- Listing opaque Artifacts and deriving document identity from type, filename,
  or digest was rejected because it admits non-document Artifacts and would
  merge or misclassify submissions.
- Offset paging was rejected because concurrent inserts shift boundaries.
  Keyset paging provides stable traversal; Refresh intentionally starts a new
  snapshot-like traversal and can reveal new submissions/state.
- The main compatibility risk is extending `SourceSubmission`. Repository,
  engine, adapter, and fixture call sites must be found with a full-tree search
  and updated together. Contract tests must prove only the source stage can
  register a document.
- Exact atomic rollback depends on retaining the current single repository
  transaction in `complete_outputs`; implementation must not add a second
  commit between Artifact and catalog inserts.

## Test Strategy

- Contract tests for source metadata validation/redaction, catalog-registration
  invariants, exact list response schema, safe field exclusions, action
  eligibility, cursor bounds/parsing, and API 422/503 envelopes.
- Ingestion engine regression tests update every `SourceSubmission` caller and
  prove confirmation registers exactly once while failures before source
  publication and preflights register nothing.
- PostgreSQL integration covers migration, equal-name/equal-digest distinct
  rows, deterministic ties, multipage traversal, Run-state refresh, atomic
  rollback, and reconnect/restart readback. If Docker remains unavailable, keep
  the scenario collected and report the environment residual explicitly rather
  than substituting an in-memory persistence claim.
- Browser interaction tests cover initial load, Refresh, Load more, load-more
  retry with retained rows, stale response rejection, explicit unavailable
  values, Run navigation, both inspector actions, omitted unsupported actions,
  and upload-dialog availability in every state.
- Visual regression covers the eight-state matrix at 1440 x 900 and 644 x 900,
  manifest integrity, pixel comparison, scoped table overflow, action geometry,
  page-level non-overlap, and S-024 upload/inspector regression.
- Run the focused workbench/trace/ingestion suites, migration checks, full
  non-Docker test suite, and enabled Chrome visual suite. Preserve documented
  environment limitations for Docker-backed tests.

## Implementation Checklist

- [ ] `deploy/local/migrations/versions/0006_document_submissions.py`: create
  and downgrade the additive catalog and keyset index.
- [ ] `src/kb2_runtime/ingestion_engine/contracts.py` and `engine.py`: validate
  bounded source display metadata and pass typed registration at source
  publication.
- [ ] `src/kb2_runtime/trace/contracts.py`, `repositories.py`, and `service.py`:
  define registration/list records, enforce atomic registration, and implement
  the safe keyset query.
- [ ] `src/kb2_runtime/workbench/contracts.py`, `documents.py`, and `api.py`:
  define the strict list contract, projection/cursor codec, and GET endpoint.
- [ ] `src/kb2_runtime/workbench/static/workbench.js` and `workbench.css`:
  render table/paging/states/actions while preserving S-024 modal and inspector.
- [ ] `tests/contract/test_trace_contracts.py`,
  `test_ingestion_engine.py`, and `test_workbench_documents.py`: cover durable
  boundaries, API projection, paging, and safety.
- [ ] `tests/integration/test_ingestion_engine_e2e.py` or a focused document
  catalog integration module: cover persistence, repeated submissions,
  ordering, state changes, rollback, and reconnect.
- [ ] `tests/contract/test_workbench_browser.py` and
  `tests/visual/baselines/s028/`: add interaction, geometry, state, and reviewed
  visual evidence without changing older baselines.
- [ ] Run focused and regression verification; record any Docker-only residual
  in the Story Pipeline run log.

Implementation ownership is intentionally grouped by boundary: migration and
trace persistence; ingestion source registration; workbench API/service; web
UI and browser fixtures; automated/visual evidence. If work is parallelized,
each group owns only its listed files and must coordinate the typed contracts
before editing shared call sites.

## 2026-09-15 Visual Parity Repair

The user confirmed a presentation-only repair against UI-003 and UI-013. It
does not change the document API, persisted data, authoritative state labels,
upload/preflight, refresh, paging, Run navigation, Artifact eligibility, or the
existing 30 x 30 accessible actions. Prototype control chrome, synthetic copy
and values, 26 px controls, start-Ingestion, Query, and invented `INDEXED`
semantics remain excluded.

Implementation is limited to `workbench.js` and page-local `workbench.css`:

- Replace the generic stacked Documents heading with a `文档实验` 22 px/800
  inline title and 12 px truthful purpose copy. Use the reference rhythm of
  `16px 16px 10px`, a 2 px ink bottom rule, and an approximately 57 px desktop
  band. Keep Refresh and the same upload handler at right; its shorter visible
  label may be `上传文档` without changing dialog behavior.
- Add a stable approximately 30 px, 11 px muted summary strip under the title.
  It reports client-known facts only: loaded item count for populated/empty,
  `正在读取持久化文档` while loading, and `文档数量暂不可用` on initial error.
  It must not claim a total while a next cursor exists.
- Align the populated table to the reference with `min-width:900px`, automatic
  column sizing, 12.5 px body type, `6px 10px` header padding, `7px 10px` body
  padding, a 2 px ink header rule, soft horizontal row rules, and no vertical
  cell borders. Target approximately 49 px rows; do not retain the current
  fixed 28/10/12/16/15/10/9 percentage tracks.
- Compose the first cell as a framed 26 x 34 px document glyph using the
  existing Lucide `file` asset plus a two-line min-width-zero text block.
  Ellipsize filename and source Artifact ID visually, preserve their complete
  DOM text, and expose complete values through `title`; byte size remains on
  the muted metadata line.
- Render processing class as an 11 px zero-radius monospace outlined label and
  Profile as 11.5 px monospace. Render the unchanged complete Run ID as a
  single-line ellipsized 11.5 px monospace link in `var(--color-info)`, with
  full text and `title` retained. Keep server-owned Chinese status labels and
  the current semantic status tones.
- Below 900 px, title/purpose and commands may wrap, but the summary strip must
  not overflow. `.document-table-wrap` remains the only horizontal scroller,
  retains the 900 px table minimum, and all actions remain at least 30 px.

Update `test_s028_document_list_visual_matrix` with reference-oriented geometry
and computed-style assertions: approximately 57 px desktop title band, 30 px
summary strip, 12.5 px table type, 2 px header rule, no vertical cell border,
single-line filename/Run layout, blue Run link, monospace class/Profile/Run,
and full diagnostic values despite ellipsis. Preserve the existing populated,
empty, loading, error, narrow-overflow, paging, stale-response, inspector focus,
and unsupported-action assertions. Intentionally regenerate and review only the
eight S-028 baseline PNGs and their manifest hashes at 1440 x 900 and 644 x 900;
older Story baselines remain unchanged. This makes parity measurable rather
than proving only agreement with a newly recorded self-baseline.

## Open Questions

None. Product behavior is fully specified by S-028; this design resolves its
API, persistence, paging, action, responsive, and verification choices.

## Approval

Approved on 2026-09-14 by the `story-pipeline-agent S-028` invocation. Proceed
directly to implementation; no separate design approval gate is required.

## Change History

- **2026-09-14:** Created the just-in-time design from the confirmed S-028
  contract, exact UI anchors, S-024 dependency, and current trace/workbench
  implementation. Approved for immediate Story Pipeline development.
- **2026-09-15:** Added the user-confirmed UI-003/UI-013 visual parity repair
  for the Documents title, truthful summary strip, table geometry, document
  identity hierarchy, diagnostic typography/colors, responsive constraints,
  and reference-oriented visual verification. Product behavior is unchanged.
