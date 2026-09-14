# Story Design: S-025 - Query Lab And Evidence UI

## Status

Approved for Story Pipeline diagnostic-parity repair.

## Story Contract Snapshot

- Story: `S-025`, confirmed 2026-09-11 and implemented 2026-09-13.
- Repair base: `main@6118e85`; delivery branch
  `feature/s-025-query-lab-diagnostic-parity`.
- Repair target: implement the useful diagnostic behavior in UI-005, UI-008,
  and UI-013 against the current post-S-028 code without changing the query
  engine contract.
- Exact sources checked: the S-025 contract; `docs/ui/reference.md#UI-005`,
  `UI-008`, and `UI-013`; prototype `isQuery` at archive entry line 778 and
  `artOpen` at line 1451; current Query workbench service/client/styles;
  Query/browser tests and S-025 visual manifest; S-024 Inspector behavior;
  S-027 diagnosis-route context; and S-028 document-submission persistence.
- Material decisions requiring approval: None. The user's instruction to apply
  the recommended bounded repair authorizes this design and immediate
  development.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Preserve the delivered server-owned single eligible Search Artifact and Query Profile selection, rotating single-use preflight, external-stage acknowledgement, submit/poll/Stop authority, and stale-response rejection. Improve only option labels and compact plan presentation. | Existing service/API authority tests remain green. Browser tests cover loading, invalidation after input changes, external acknowledgement, submit failure/retry, polling, Stop, and requested S-027 Run context. |
| 2 | Add a bounded workbench-only projection built from persisted candidate Artifacts and the exact pinned `SearchIndexResult/v1`: actual stage duration, candidate excerpt/document label/friendly locator, plus a server-owned decision-path matrix keyed by exact document and Chunk identity. Keep every retrieval/fusion/rerank candidate set as an independent tab. | Unit/API tests validate exact joins, deterministic order, bounds, missing/corrupt Artifact fallbacks, no rescoring, and no vectors. Browser tests prove independent tabs and that the decision path is rendered only from the returned projection. |
| 3 | Make Evidence summary-first: citation key, safe document label, excerpt, friendly locator, context result/rationale, and two distinct command classes. Validated answer citations exist only in an `ANSWERED` final result; Evidence source preview exists whenever a verified `sourceArtifactId` and locator exist, regardless of final state. Put UUIDs, structured locators, contributors/scores, hierarchy, and table IDs in an expandable diagnostic section. | Service tests cover safe labels/locator formatting and source lineage. Browser tests distinguish citation and preview commands, open S-024 Inspector from answered and non-answered Evidence, and assert selected locator, focus/Escape return, and URL context preservation. |
| 4 | Continue rendering exactly `ANSWERED`, `CLARIFICATION_REQUIRED`, `ABSTAINED`, or `FAILED` as product final states. Verification failure and bounded repair are compact subordinate Trace events; only a citation-valid `ANSWERED` response may expose answer text and citation actions. | Contract/browser tests retain the no-answer invariant and exercise clarification, shortage abstention, successful repair ending in `ANSWERED`, and exhausted repair ending in `FAILED`. |
| 5 | Preserve pre-execution external disclosure and acknowledgement exactly as returned by preflight. Additive diagnostic lookups read only already pinned/persisted local Artifacts and safe document metadata; they never invoke a provider or expose credentials, paths, raw payloads, or vectors. | Tests verify disclosure invalidation and safe failure codes, and recursively assert the Query response contains no vector values, storage locators, credentials, provider response bodies, or unsafe filenames. |
| 6 | Rebalance the desktop workbench toward control/retrieval scanning, retain the superior narrow stacked layout, compact the stage table to duration, and use progressive Evidence detail. Replace the state-only visual set with realistic Chinese fact, table, hierarchy, verification/repair, and Inspector scenarios at 1440 x 900 and 644 x 900. | Reviewed manifest-backed goldens and geometry/accessibility checks cover pane proportions/order, table overflow, long localized content, expandable detail, source drawer, focus, and no overlap or document-level horizontal overflow. |

## Current Code Findings

- `QueryWorkbenchService` already owns Profile/index eligibility, preflight
  rotation and single consumption, external acknowledgement, Run submission,
  owner-only Stop, ordered Trace reading, candidate Artifact validation,
  Evidence parsing, final-response validation, and lineage-proven source
  resolution. These authorities stay unchanged.
- `run()` currently projects `startedAt` and `endedAt`, but not the already
  established workbench `durationMs` convention. The browser consequently
  spends two columns on timestamps instead of exposing the useful elapsed time.
- `_candidate_rows()` returns rank, Chunk ID, scores, contributions, locators,
  and optional rerank decision. It does not load `SearchIndexResult/v1`, so the
  client hard-codes candidate excerpt to `不可用`; document identity and a
  readable locator are also absent.
- Candidate sets are correctly independent, while fusion/rerank/context facts
  are split across tabs and a context table. The browser currently performs a
  partial Chunk-only Evidence/context join. There is no authoritative
  cross-stage decision-path projection suitable for comparing how one Chunk
  moved through the resolved plan.
- Evidence source resolution walks only persisted index lineage and verifies a
  locator against an Inspector-capable Canonical Document or Chunk Set. This is
  the correct trust boundary. However, the Evidence citation-key control is
  also used as the source-preview control and is suppressed unless the final
  state is `ANSWERED`, preventing diagnosis of abstained and failed results.
- Evidence currently exposes long excerpts followed by raw JSON locators and a
  large definition list. The reference instead presents document identity,
  locator, context status, rationale, and source preview first, with technical
  identity subordinate.
- S-028 now atomically persists a sanitized leaf `display_filename` in
  `document_submissions`. `list_document_submissions()` can expose it only by
  paging the catalog; Query Lab needs an exact bounded lookup for already
  lineage-proven source Artifact IDs. Older artifacts legitimately have no
  registration and require a non-invented fallback label.
- The current three tracks are approximately `26% / 41% / 33%`. The answer
  pane consumes too much width for routine diagnosis, while the control and
  retrieval panes wrap early. The below-900 px stacked order already behaves
  better than the prototype's compressed desktop row and must remain.
- The existing eight S-025 goldens cover four final states at two widths, but
  all share one long English Evidence fixture. They do not visually prove a
  table cell, hierarchical multi-evidence, distinct source preview, successful
  repair, or the open Inspector.

## Proposed Approach

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

### Layout And Responsive Behavior

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

## Relevant Impacts

- **UI:** Refactor only the Query Lab render helpers and Query-specific styles.
  Preserve the workbench shell, local Archivo/Lucide assets, shared primitives,
  S-024 Inspector implementation/selectors, and S-027 route helpers.
- **API/read model:** Add backward-compatible fields to
  `workbench-query-run/v1`: `durationMs`, safe candidate/Evidence display facts,
  and `decisionPath`. Existing fields and endpoint paths remain valid.
- **Repository/data:** Add an exact bounded read method for S-028
  `document_submissions`. No write path, database table, migration, Artifact
  contract, or Run schema changes.
- **Security:** Source labels come only from S-028-sanitized metadata after
  verified lineage. Excerpts and locator labels are bounded and text-node
  rendered. Raw vectors, storage paths, prompts, credentials, endpoints,
  provider bodies, arbitrary metadata, and unsafe exceptions remain excluded.
- **Compatibility:** Preserve one Search Artifact per Query Run, final-response
  validation, async authority, external disclosure, owner-only Stop,
  `inspector(id, origin, selectedLocator)`, and requested Run/diagnosis URL
  context. Older source artifacts work with safe fallback labels.

## Deterministic Visual Contract

Replace the repetitive state-only fixture set with contract-valid Chinese
fixtures. Keep exact S-022 capture conditions and RGBA comparison policy. The
revised manifest contains these reviewed captures:

| File stem (both `-1440.png` and `-644.png`) | Scenario | Required visible evidence |
|---|---|---|
| `query-fact-answered` | high-precision fact, `ANSWERED` | independent retriever tabs, candidate excerpts/labels/locators, decision path, validated citation, compact duration |
| `query-table-answered-inspector` | table-cell answer with Inspector open | table/cell locator, table Evidence, distinct source-preview command, synchronized S-024 table/source selection |
| `query-hierarchy-answered` | hierarchical multi-Evidence answer | parent/child Evidence, multiple contributors/citations, inclusion rationale, progressive technical detail |
| `query-clarification-required` | ambiguous question | clarification action, diagnostic Evidence source preview, no answer or answer citation |
| `query-abstained` | unanswerable/shortage | excluded decision path, shortage facts, Evidence preview where lineage exists, no answer |
| `query-repair-answered` | initial verification failure then bounded repair success | authoritative `ANSWERED`, ordered verification/repair detail, unchanged Evidence identity |
| `query-repair-exhausted` | verification failure and exhausted repair | authoritative `FAILED`, failure codes and attempts, Evidence source preview, no answer/citation |

This yields fourteen main goldens. The open Inspector scenario at both widths is
part of the table case rather than a decorative separate fixture. Use real
typed locator shapes, distinct Chinese excerpts, sanitized filenames, multiple
retriever contributions, and deterministic timestamps/scores. Do not use
prototype IDs, scores, provider names, or scenario controls as production data.

Loading, empty options, external acknowledgement, active Stop, polling failure,
tab keyboard navigation, collapsed/expanded details, unavailable legacy label,
and source-preview focus return are DOM/interaction assertions rather than more
goldens. Capture tests assert exact viewport and font prerequisites,
`documentElement.scrollWidth <= innerWidth`, stable desktop tracks/narrow order,
positive target sizes, labelled table overflow, no overlap, and selected source
locator visibility.

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

- Extend Query workbench unit tests for typed index loading, excerpt bounds,
  filename precedence/fallback, typed locator labels, exact identity joins,
  deterministic decision-path ordering, duration, malformed/missing artifacts,
  bounded lineage and batched repository lookup, and vector non-disclosure.
- Extend repository integration tests for exact source-ID lookup, empty input,
  cap/deduplication, unknown/pre-S-028 IDs, sanitized returned records, and no
  cross-source leakage. Existing S-028 atomic write/paging/restart tests remain
  unchanged.
- Extend API tests to validate additive response fields while retaining all
  options/preflight/submit/Stop and final-validation contracts.
- Extend browser tests for distinct citation/source commands in every applicable
  final state, server-rendered decision path, independent candidate tabs,
  collapsed Evidence/attempt detail, duration, Inspector locator/focus/Escape,
  and S-027 Run/query-string preservation.
- Capture and compare all fourteen revised goldens under the exact pinned
  environment. Run S-025 focused tests plus S-024 Inspector, S-027 route,
  S-028 document catalog/persistence, S-022 shell, and broader non-Docker
  workbench regressions.

## Implementation Checklist

- [ ] Add exact bounded S-028 document-submission lookup at the repository read
  boundary with focused integration tests.
- [ ] Extend Query workbench parsing/projection with the pinned index display
  map, safe labels/excerpts/locators, actual duration, and server-owned decision
  path; keep engine and durable schemas unchanged.
- [ ] Refactor Query Lab rendering for compact stages, independent candidate
  tabs plus decision path, progressive Evidence details, and distinct citation
  versus source-preview actions.
- [ ] Rebalance desktop panes and preserve the below-900 px stack and S-024
  full-width Inspector.
- [ ] Replace the S-025 fixture/manifest/goldens with realistic fact, table,
  hierarchy, clarification, abstention, repair-success, repair-exhaustion, and
  Inspector coverage.
- [ ] Run focused, visual, Inspector, route-context, document-safety, and broad
  non-Docker workbench regressions; record any environment-only residual.

## Open Questions

None. The authorized Story Pipeline may proceed directly to development.

## Approval

Approved by the user's 2026-09-14 instruction to execute the recommended S-025
diagnostic-parity repair. This design records only additive workbench projection
and exact repository lookup choices; it introduces no product, engine, durable
schema, migration, or external-call decision requiring separate approval.

## Change History

- **2026-09-13:** Created the initial just-in-time design and delivered the
  API-backed S-025 workflow.
- **2026-09-14:** Revised for the first UI-reference parity repair and delivered
  the three-pane Query Lab with eight final-state baselines.
- **2026-09-14:** Re-evaluated `main@6118e85` after S-028 and approved this
  bounded diagnostic-parity repair: safe candidate/source display facts,
  server-owned decision path, separated citation/source actions, actual stage
  duration, progressive Evidence, rebalanced panes, and realistic visual cases.
