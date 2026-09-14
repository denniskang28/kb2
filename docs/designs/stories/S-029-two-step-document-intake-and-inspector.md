# Story Design: S-029 - Two-Step Document Intake And Unified Document Inspector

## Status

Approved for Story Pipeline implementation.

## Story Contract Snapshot

- Story: `S-029`, confirmed 2026-09-15.
- Context: the self-contained S-029 contract, implemented dependencies S-024
  and S-028, current code/tests, and exact UI-003, UI-005, and UI-013 anchors.
- Material decisions requiring approval: None. The confirmed Story assigns
  renderer, endpoint, paging, and lineage-query choices to this design, and
  the Story Pipeline invocation authorizes immediate development.
- Boundary: refine the existing intake and document-list interactions without
  changing Profile resolution precedence, ingestion execution, Artifact
  schemas, immutable Run semantics, or the general Artifact inspector used by
  other workbench routes.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Recompose the current upload dialog as an explicit file-only step 1 and a server-preflight/Profile step 2. Selecting or replacing a file invalidates the prior token immediately; preflight bytes remain process-local and create no `document_submissions` row. | Service/API tests assert preflight-only, cancel, replacement, and failure leave the catalog unchanged. Browser tests cover step identity, file replacement, loading/error, Escape, and focus restoration. |
| 2 | Keep the existing resolver authoritative. Step 2 renders returned detector facts, automatic evidence, candidate radios, selected rationale, resolved stages, and plan digest. Candidate change keeps the existing atomic token claim/rotation and replaces all confirmable state. | Existing candidate-selection tests are extended for fresh digest/disclosure, stale response suppression, and no submit authority during a switch. Browser assertions cover automatic and explicit states. |
| 3 | The final command sends only the current token-bound Profile and acknowledgement. Existing `submit()` digest/disclosure revalidation remains the single persistent path and redirects to the created Run. | Contract and API tests cover disabled confirmation, expiry, stale plan, missing acknowledgement, double-submit, failed engine creation, exactly one source registration, and Run routing. |
| 4 | Add an additive `inspectDocument` action to the document-list projection. Replace the two Source/latest-output controls in the Documents table with one Lucide eye button that opens the document endpoint by exact `sourceArtifactId`. | Projection/source tests assert one eligible action, no inert controls, and no client use of arbitrary output IDs. Browser tests cover unavailable/eligible rows and precise accessible labeling. |
| 5 | Add a document inspector summary plus an authorized source-content endpoint. Registered PDFs render through Chromium's native PDF viewer using same-origin, range-capable bytes; source IDs, never storage locators, form the URL. Unsupported formats expose structured/text views or an explicit preview-unavailable state. | Integration tests cover exact registration authorization, PDF media/range headers and invalid ranges, missing bytes, non-PDF safety, and no path leakage. Browser tests use a representative PDF and navigate to a returned page locator. |
| 6 | Resolve the exact submission Run and its succeeded descendant Artifacts server-side. Lazy paged view endpoints expose Canonical elements/structure/tables, Chunks, metadata, and bounded lineage. Chunk items include stable IDs, bounded text, token/parent/children facts, source elements, and every citation locator. | Contract tests validate schemas, per-view bounds, all Chunk facts, conditional tabs, stable IDs, multiple citations, and safe-field exclusion. PostgreSQL integration covers partial and complete Run projections. |
| 7 | The document drawer has one persistent source-preview pane and a tabbed diagnostic pane. Selecting an element, table, Chunk, or citation applies its server-returned locator: PDF changes the viewer page and updates a locator/highlight summary; existing paired stable-ID highlighting is reused where a native renderer cannot draw a region overlay. | Browser tests cover element/table/Chunk/citation-to-preview synchronization, multiple citation locators, partial views, unsupported locator kinds, missing Run/ChunkSet, and remaining-tab usability. |
| 8 | A repository query proves exact source registration and descendant lineage inside the registered Run. Responses are allowlisted, paged, size-capped projections; source bytes are available only through the registered-source preview endpoint. | Adversarial contract tests try unrelated Run/Artifact IDs, forged cursors, oversized content, unsafe manifest metadata, raw vectors, provider payloads, and storage/path strings. Repeated-filename/digest submissions remain distinct. |
| 9 | Reuse the workbench dialog/drawer focus containment, inert background, scroll lock, UI-013 tokens, and scoped responsive overflow. The intake dialog has fixed header/footer and scrolling body; the inspector becomes a full-height split drawer that stacks below 900 px. | Reviewed 1440 x 900 and 644 x 900 screenshots cover both intake steps, PDF/Chunks, partial/unavailable, loading, expired, and error states. Geometry and keyboard tests assert reachable controls, no page overflow/overlap, focus trap, Escape, and return focus. |

## Current Code Findings

- `DocumentWorkbenchService` already owns a five-minute, process-local
  `_Preflight` containing the bytes and token-bound Profile/digest/disclosure.
  `select_candidate()` atomically consumes the old token and returns a rotated
  one; `submit()` re-resolves and rejects selection, plan, or disclosure drift
  before it persists anything. These are the correct S-029 submission
  authority and must not be replaced.
- The current dialog shows the file and Profile Set fields together, then
  appends all preflight sections in one long surface. It already has request
  generations, stale-response suppression, external acknowledgement, focus
  containment, and Run redirect behavior; the needed change is state/layout
  decomposition, not a second upload implementation.
- A saved Profile workspace contains a Profile Set. DES-007 automatic and
  explicit precedence applies inside that configured set. The client must not
  rank separate Profile Sets. Step 1 is file-only; at entry to step 2 the user
  selects the saved Profile Set when more than one valid ingestion set exists,
  then requests detection/resolution. With exactly one valid set it is selected
  without an extra choice. The existing bounded
  `GET /api/workbench/profiles?kind=ingestion` supplies those server-owned
  options; invalid sets remain visible as unavailable and cannot start
  preflight.
- The persisted catalog already proves a source registration by joining
  `document_submissions`, the exact `ingestion.source` output, its ingestion
  Run, and resolution evidence. The current list exposes arbitrary source and
  latest-output Artifact IDs as separate actions. S-029 should add one
  document eligibility flag and resolve the detailed Artifact set only after
  the eye action is invoked.
- The generic `/api/workbench/artifacts/{id}` projection can display one
  Canonical or Chunk Artifact, but it cannot prove that an arbitrary ID belongs
  to a selected document, combine source/Canonical/Chunk views, or page large
  schemas. It remains valid for Run, Query, and evaluation diagnostics; the
  document-centered endpoints are additive rather than a breaking rewrite.
- `TraceRepository` has exact source lookup, Run trace/plan reads, manifest
  reads, and a Run Artifact list, but no single descendant query constrained to
  a registered source. A bounded recursive query can add that proof without a
  migration because `document_submissions`, `artifact_lineage`, Artifacts, and
  stage attempt state already persist every required relationship.
- `opaque.bytes/v1` is the registered source. `canonical.document/v1` embeds
  structure and tables; `chunk.set/v1` already contains `token_count`,
  `parent_chunk_id`, `child_chunk_ids`, all source element IDs, and all
  citation locators. The current generic Chunk projection drops the relation
  and token facts and truncates content, so S-029 needs a richer bounded view.
- `pypdf` is already installed for parsing, but no raster renderer exists.
  Serving an authorized same-origin PDF to Chromium's native PDF viewer gives
  real page content and page navigation without adding PyMuPDF, Poppler, or a
  client PDF library. Native PDF regions cannot be reliably overlaid; the UI
  therefore navigates to the page and shows the normalized region in the live
  locator summary, as allowed by AC 7's renderer-qualified synchronization.

## Proposed Approach

### Intake State Machine

Keep the dependency-free DOM client and current preflight endpoints. Model the
dialog explicitly as:

```text
FILE -> PROFILE_SET_REQUIRED | PREFLIGHTING -> READY
                                      |          |
                                      v          v
                                   ERROR      SUBMITTING -> ROUTED
                                                   |
                                                   v
                                                ERROR
```

`FILE` contains only the native local-file control, selected filename/size,
Cancel, and `下一步`. It does not display candidate Profiles and sends no bytes
until the operator requests preflight. `下一步` opens the Profile/preflight
step and loads saved ingestion Profile Sets. If one valid set exists, start
preflight immediately; if several exist, show a compact Profile Set selector
and keep `检测并匹配` disabled until one is chosen. This selector chooses the
configuration container, not an inner Profile and does not alter DES-007.

`PREFLIGHTING` immediately clears the old token, resolved plan, acknowledgement,
and final command. `READY` uses only the latest response and renders:

- filename and every returned `detected` fact;
- `自动匹配` plus the returned compatible inner Profile candidates;
- evaluated matched/unmatched rules and the automatic selection tier;
- the currently bound selected Profile and rationale;
- resolved stage/Plugin rows, plan digest, local persistence notice, and any
  selected external-stage disclosure.

Changing the inner Profile uses the existing selection endpoint and rotates
the token. Changing the file or Profile Set discards the old token through
`X-Replaces-Preflight-Token` before a new request. Back from step 2 to step 1
also invalidates the token, because a hidden confirmable authority is unsafe.
Cancel/close discards client state; add an idempotent
`DELETE /api/workbench/documents/preflights/{token}` so the service can release
retained bytes immediately rather than waiting for TTL. A missing/expired token
returns the standard safe problem but DELETE itself is idempotent (`204`).

The final label is `开始 Ingestion`. It exists only in `READY`, is disabled
while acknowledgement is required, and sends the current selected Profile.
Submission remains the existing exactly-once token claim. A duplicate click is
blocked locally and the consumed token makes a repeated request fail without a
second Run. Successful `202` routing remains
`/workbench/runs?run=<id>&legacy=ingestion`.

### Document-Centered Projection

Add this summary endpoint:

```http
GET /api/workbench/documents/{source_id}/inspector
```

It returns `workbench-document-inspector/v1` with only:

```json
{
  "source": {
    "id": "uuid", "filename": "sample.pdf",
    "mediaType": "application/pdf", "byteSize": 1234,
    "registeredAt": "..."
  },
  "latestRun": {"id": "uuid", "state": "SUCCEEDED"},
  "preview": {
    "kind": "pdf", "contentUrl": "/api/workbench/documents/<id>/content",
    "pageCount": 8, "reason": null
  },
  "tabs": [
    {"id": "canonical", "state": "available", "artifactId": "uuid"},
    {"id": "structure", "state": "available", "artifactId": "uuid"},
    {"id": "tables", "state": "available", "artifactId": "uuid"},
    {"id": "chunks", "state": "available", "artifactId": "uuid"},
    {"id": "metadata", "state": "available"},
    {"id": "lineage", "state": "available"}
  ],
  "artifacts": {
    "source": {"id": "uuid", "artifactType": "opaque.bytes", "schemaRevision": "v1"},
    "canonical": {"id": "uuid", "artifactType": "canonical.document", "schemaRevision": "v1"},
    "chunks": {"id": "uuid", "artifactType": "chunk.set", "schemaRevision": "v1"}
  },
  "metadata": {"format": "pdf", "documentClass": null, "profileId": "..."}
}
```

The summary first proves `source_id` is an exact document submission, then
uses its registered `run_id`; in the current model that is the deterministic
latest related Run for this distinct submission. It does not search by filename
or digest and does not attach later submissions. A new repository method,
`list_document_artifact_manifests(source_id, run_id, limit=128)`, follows
descendants from that exact source through `artifact_lineage`, restricts them
to succeeded attempts in the same Run, and orders by `created_at, id`. The
service selects the last succeeded `canonical.document/v1` and
`chunk.set/v1` in that order. Tables/structure are capabilities of the selected
Canonical document. A running or failed Run naturally returns partial tabs.

The summary returns an explicit tab state/reason for expected views whose
Artifact is not yet available (`RUN_IN_PROGRESS`, `CANONICAL_UNAVAILABLE`,
`CHUNKSET_UNAVAILABLE`, `SOURCE_PREVIEW_UNAVAILABLE`). The client omits a tab
only when it is inapplicable; a temporarily unavailable expected tab remains
visible with its explanation. No view failure prevents metadata, lineage, or
an already available sibling view from loading.

The list response remains `workbench-document-list/v1`. Add
`actions.inspectDocument: bool`; retain the old optional Artifact ID fields for
wire compatibility during rollout, but the Documents client stops rendering
or invoking them. A legitimate registered source with an available manifest
sets the flag true and renders exactly one eye control labelled
`查看文档内容与 Chunks`.

### Bounded View APIs

Load view data only when its tab is selected:

```http
GET /api/workbench/documents/{source_id}/inspector/views/{view}?limit=25&cursor=<opaque>
```

`view` is allowlisted to `canonical`, `structure`, `tables`, `chunks`, and
`lineage`. Metadata is small and stays in the summary. Defaults and maxima are:

| View | Default | Maximum | Item bound |
|---|---:|---:|---|
| Canonical/structure | 50 | 100 | text 2,048 chars; IDs, kind, order, parent, level, locator |
| Tables | 10 | 20 | 512 returned cells per page; cells retain spans/header facts |
| Chunks | 25 | 50 | content 4,096 chars plus `truncated`; max 128 citations and 64 children from schema |
| Lineage | 50 | 128 | safe manifest identity, type/schema, producer, parents, summary |

The opaque cursor encodes version, exact selected immutable Artifact ID, view,
and next offset. The server rejects malformed, mismatched, negative, or
out-of-schema offsets; a cursor cannot select a different Artifact. Since
Artifacts are immutable, offset paging cannot drift. The service refuses to
parse a structured Artifact over 64 MiB and returns a per-view
`DOCUMENT_VIEW_TOO_LARGE` unavailable response; it never falls back to raw
content. Returned objects use explicit Pydantic workbench contracts rather than
unbounded `dict[str, Any]` at the API boundary.

Canonical and structure share the chosen Artifact but differ in presentation:
Canonical is reading-order rows; structure returns the same bounded elements
with parent IDs for the client tree. Tables page table objects and their cells
without inventing text. Chunks include `id`, `content`, `truncated`,
`tokenCount`, `sourceElementIds`, `parentChunkId`, `childChunkIds`, and every
`{elementId, locator}` citation. Lineage exposes only source and descendant
manifests selected by the repository proof. It excludes content digests unless
needed for an existing public identity, storage locators, configuration
payloads, raw vectors, provider payloads, and paths.

### Authorized Source Preview

Add:

```http
GET /api/workbench/documents/{source_id}/content
```

The service repeats exact document-registration authorization; it never
accepts an Artifact ID other than the path's registered source. It reads bytes
through `ArtifactService`, not a locator. `application/pdf` sources are served
inline with `Accept-Ranges: bytes`, `Cache-Control: private, no-store`,
`X-Content-Type-Options: nosniff`, and
`Cross-Origin-Resource-Policy: same-origin`. Accept only one valid `bytes`
range and cap a partial response to 1 MiB; return `206` with exact
`Content-Range`, or `416` for invalid/multiple ranges. A request without Range
may return the complete source because intake already caps it at 16 MiB.

The endpoint allowlists PDF and safely decodable plain text. Text is capped at
256 KiB and served as UTF-8; other formats return `PREVIEW_FORMAT_UNAVAILABLE`
rather than attachment/download or browser sniffing. Filenames are used only
as the already validated display leaf in `Content-Disposition: inline` and are
RFC 5987 encoded. `pypdf.PdfReader` may provide bounded page count at summary
time; encrypted, malformed, or excessive-page PDFs remain downloadable to no
client path and receive an explicit preview-unavailable reason. No PDF text
extraction or rasterization is added.

The client embeds `contentUrl#page=N` in an `<object type="application/pdf">`
inside the source pane. A PDF locator selects `page_number`, reloads the object
only when the page changes, and shows the normalized `[x0,y0,x1,y1]` region in
the live locator summary. Other locator kinds use the existing readable
locator label and stable-ID pairing; unsupported graphical navigation is
honestly marked.

### Unified Inspector Client

Add `documentInspector(sourceId, returnFocus)` alongside the existing generic
`inspector()`; do not change callers from Run/Query/Evaluation. The new drawer
contains:

```text
header: filename, source ID, Run status, close
div.document-inspector-workspace
  section.document-preview-pane
    preview toolbar / page control / live locator summary
    object.pdf-preview | pre.text-preview | unavailable
  section.document-diagnostic-pane
    tablist
    paged tabpanel
      object list/tree/table/chunk list + selected detail
footer/load-more where applicable
```

Tabs come only from the server summary. Tab data is cached per immutable
Artifact/cursor within the open drawer, with request generations preventing a
late response from replacing a newer selection. Chunk rows remain compact;
the selected Chunk detail shows its complete bounded excerpt and relation
facts. Each citation is a separate keyboard-reachable source command, so no
first-citation-only behavior returns. Canonical/table/Chunk selection calls one
`selectDocumentLocator(stableId, locator)` helper to update paired highlights,
preview page, locator summary, and selected detail consistently.

At desktop the drawer is `min(1180px, calc(100vw - 32px))` with a roughly
`44% / 56%` preview/diagnostic split and no page-level scroll. Below 900 px it
uses the viewport width, stacks preview above diagnostics, keeps the header and
tabs visible, and gives each pane scoped overflow. The native PDF object has a
stable minimum height rather than resizing with content. Existing dialog
semantics are retained: labelled `role=dialog`, inert background, scroll lock,
focus trap, Escape/close, scrim close, and exact origin focus restoration.

### Failure, Security, And Observability

Use `workbench-problem/v1` with stable codes:

- `DOCUMENT_NOT_FOUND`/404 for an unknown or non-registered source;
- `DOCUMENT_INSPECTOR_UNAVAILABLE`/503 for repository/read failure;
- `DOCUMENT_VIEW_INVALID`/422 for view, limit, or cursor errors;
- `DOCUMENT_VIEW_UNAVAILABLE`/409 for a known but currently absent view;
- `DOCUMENT_VIEW_TOO_LARGE`/413 for the structured parse cap;
- `SOURCE_CONTENT_UNAVAILABLE`/404, `PREVIEW_FORMAT_UNAVAILABLE`/415, and
  `SOURCE_RANGE_INVALID`/416 for the content endpoint;
- existing preflight/submission codes remain unchanged; explicit DELETE is
  idempotent.

Never place exception messages in responses. Log code, source UUID, Run UUID,
view, selected Artifact UUID, returned item count, duration, and outcome at the
existing application logger boundary; do not log filenames, content, locators,
preflight tokens, filesystem paths, or storage locators. This Story does not
add identity/tenant authorization; exact registered-source authorization is
the correct local Lite boundary.

## Relevant Impacts

- **API:** additive DELETE-preflight, document inspector summary, paged view,
  and source-content endpoints; additive `actions.inspectDocument` on list
  items. Existing generic Artifact APIs remain supported.
- **Data:** no migration and no schema changes. Add one bounded recursive read
  query over existing document, Run, attempt, Artifact, and lineage tables.
- **UI:** two explicit intake steps and one new document-centered drawer; the
  Documents row changes from two Artifact controls to one eye control.
- **Security:** source content is reachable only by a registered source UUID,
  served same-origin/no-store/nosniff, and never exposes its store locator.
- **Compatibility:** existing preflight/selection/submit bodies and response
  version stay valid. Old list Artifact action fields may be removed in a later
  version after all clients use `inspectDocument`.
- **Rollout:** endpoints can land before the client. The client should switch
  to the new eye action only after summary/view/content contract tests pass.

## Alternatives And Risks

- Serving generated page PNGs would allow exact region overlays, but pypdf does
  not rasterize and adding PyMuPDF/Poppler materially increases image size and
  operational surface. Native Chromium PDF is sufficient for the confirmed
  representative path; region coordinates remain explicit even when the
  renderer only navigates by page.
- Returning Canonical and all Chunks in the summary is simpler but can create
  multi-megabyte responses and block narrow clients. Immutable Artifact-bound
  cursors and lazy tabs provide deterministic paging without new persistence.
- Reusing `/artifacts/{id}` would expose an arbitrary-ID entry point and cannot
  prove document ownership or select coherent source/Canonical/Chunk Artifacts.
  The document endpoint intentionally performs that join server-side.
- Choosing a Profile Set lexically or by recent update would invent a
  cross-set resolution policy. The design auto-selects only when exactly one
  valid set exists; otherwise the user chooses the configuration set before
  the existing deterministic inner-Profile resolver runs.
- Chromium's PDF plugin behavior can vary by build. Browser acceptance pins the
  repository's existing Chrome harness and separately asserts HTTP range and
  locator behavior so rendering failure degrades to a usable explicit state.
- A 64 MiB structured parse cap may reject an otherwise valid very large
  Canonical/Chunk Artifact. The safer behavior is a per-tab unavailable state;
  streaming JSON parsing is deferred until real corpus evidence justifies its
  complexity.

## Test Strategy

### Contract And Unit

- Extend `tests/contract/test_workbench_documents.py` for intake state
  invalidation, DELETE idempotency, exact confirmation authority, inspector
  selection, view contracts/cursors/bounds, full Chunk relation/citation facts,
  partial availability, safe fields, and source content/ranges.
- Add repository-query unit/contract fixtures proving unrelated, failed, or
  cross-Run descendants are excluded and deterministic type selection uses
  `created_at, id`.
- Retain existing S-024 generic Artifact tests to prove no regression for Run,
  Query, and evaluation callers.

### Integration

- Extend `tests/integration/test_trace_persistence.py` or the focused ingestion
  integration suite to submit two same-name/same-digest documents, complete a
  representative PDF Run, restart the trace/store service, and assert each
  source resolves only its own Run and descendants.
- Cover a running Run with source only, a failed Run with Canonical but no
  ChunkSet, and a successful Run with later Canonical/ChunkSet descendants.
- Read the PDF through full and sequential Range requests; verify response bytes
  equal only the registered source and headers contain no private locator.

### Browser, Accessibility, And Visual

- Extend `tests/contract/test_workbench_browser.py` with deterministic API
  fixtures for step 1, Profile Set required, automatic ready, explicit switch,
  disclosure, expired/failure, PDF/Canonical/table/Chunks, partial/unavailable,
  and pagination.
- Assert one eye action, tab ARIA semantics and arrow navigation, every citation
  command, source page synchronization, stale request suppression, focus trap,
  Escape/scrim close, and return focus.
- Add reviewed `tests/visual/baselines/s029/` captures at 1440 x 900 and
  644 x 900 for the Visual Acceptance Matrix states. Use the existing pinned
  Chrome/font/locale harness, RGBA comparison, scoped overflow assertions, and
  explicit geometry checks for fixed headers, source pane, tabs, Chunk detail,
  and reachable footer commands.
- Run the focused workbench document/browser suite, S-024/S-025 source-sync
  regressions, trace repository/integration tests, and the full non-Docker test
  suite; run the Docker persistence scenario when the environment is healthy
  and record any pre-existing Compose limitation separately.

## Implementation Checklist

- [ ] Add typed document inspector/view/action contracts in
  `src/kb2_runtime/workbench/contracts.py`.
- [ ] Add exact-source descendant query in
  `src/kb2_runtime/trace/repositories.py`; no migration.
- [ ] Extend `src/kb2_runtime/workbench/documents.py` with preflight discard,
  inspector summary, safe paged projections, cursor binding, and authorized
  source-content reads.
- [ ] Add DELETE, summary, view, and content routes plus bounded range handling
  in `src/kb2_runtime/api.py`.
- [ ] Recompose intake and add the unified document drawer in
  `src/kb2_runtime/workbench/static/workbench.js`.
- [ ] Add responsive two-step/inspector styles in `workbench.css` and
  `artifact.css`, reusing existing tokens and vendored Lucide eye icon data.
- [ ] Update contract, repository, browser, accessibility, integration, and
  visual regression tests; review all S-029 baselines before delivery close.

## Open Questions

None.

## Approval

Approved by the Story Pipeline invocation on 2026-09-15. Implementation may
proceed immediately within the confirmed S-029 contract and this design.

## Change History

- **2026-09-15:** Created and approved the just-in-time design for two-step
  intake, exact-source document projection, bounded native PDF preview, paged
  Canonical/table/Chunk views, and one document inspector action.
