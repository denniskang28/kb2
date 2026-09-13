# Story Design: S-025 - Query Lab And Evidence UI

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-025`, confirmed 2026-09-11.
- Sources checked: S-025; UI-005, UI-008, and UI-013; delivered S-015,
  S-022, and S-024 designs, executable contracts, and tests. The S-015
  generation/final-state contracts and the S-024 Artifact inspector were
  treated as authoritative dependency boundaries.
- Material decisions requiring approval: None. The `story-pipeline` invocation
  authorizes the bounded workbench API, local query coordination, and static
  browser implementation below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Add a server-owned Query Lab catalog/preflight/submit/read projection. It offers only lineage-eligible `search.index.result/v1` Artifacts and saved valid Query Profiles, validates the selected binding, compiles it on the server, returns the resolved plan/capability disclosure, and exposes Run/Stop only when the process owns an active task. | Service/API tests cover ineligible/missing indexes, wrong Profile kind, compilation errors, capability states, external acknowledgement, single-use preflight, receipt, cancellation ownership, and safe unavailable results. |
| 2 | Project the persisted query `RunTrace`, frozen plan, and typed retrieval/fusion/rerank/Evidence/final Artifacts into ordered stage rows and separate candidate/decision collections. The browser renders one tab per real retriever output and never merges or recomputes candidates/scores. | Projection fixtures and browser tests cover retrieval-only, fused, reranked, context, repair, and failed traces; assert ordering, contributor attribution, absent optional stages, and that no synthetic candidate values are rendered. |
| 3 | Parse `EvidenceSet/v1`, `FinalResponse/v1`, and, only where present, verification/generation artifacts after digest-verified reads. Reuse S-024's shared Artifact inspector for exact locator selection; citation keys navigate to the selected Evidence item's source locator. | Contract tests cover every Evidence field, bounded scores, context decisions/rationale, citation-to-locator selection, corrupt/missing Artifacts, and no raw vectors/storage paths. Browser tests exercise citation and Evidence opening the synchronized inspector. |
| 4 | Render terminal `FinalResponse` states exactly. Verification and repair attempts are trace detail, while final state remains one of `ANSWERED`, `CLARIFICATION_REQUIRED`, `ABSTAINED`, or `FAILED`; only a validated `ANSWERED` projection shows answer text/citation controls. | Fixtures cover supported answer, clarification, abstention, generation/provider failure, verification failure, repair success, and repair exhaustion; contract/UI assertions reject answer payloads for non-answered states. |
| 5 | Drive provider disclosure and execute eligibility from server-supplied resolved stages/capabilities. Require acknowledgement before submitting a plan with an external generation stage; display readiness/code without making browser probes or promising a broader offline/privacy property. | Capability/disclosure tests cover configured, unavailable, and not-configured generation; browser tests assert blocked acknowledgement and safe failure display without exposing provider responses, credentials, URLs, or question contents outside the intended controls. |
| 6 | Replace the Query Lab placeholder in the existing native-DOM workbench. Use a desktop three-part grid for controls/trace, Evidence, and result; stack or use scoped horizontal scrolling under 900 px, and retain shell/drawer/inspector keyboard behavior. | Fixture-backed browser screenshots at 1440 x 900 and 644 x 900 for the full adopted state matrix, with focus/Escape/citation interaction, document scroll-width, and element-box overlap assertions. |

## Current Code Findings

- S-015 provides `QueryEngine`, immutable `EvidenceSet/v1`, generated-answer,
  verification, and `FinalResponse/v1` contracts. The engine records the
  actual ordered Plugin attempts and bounded repair, but has only a
  programmatic `execute(plan, question_artifact, search_artifact)` entry
  point. It cannot yet materialize a browser question safely or return a Run
  ID before completion.
- `RunService` and `ArtifactService` already provide immutable plan snapshots,
  trace reads, digest-checked Artifact reads, artifact manifests, lineage, and
  `EngineKind.QUERY`. `TraceRepository` has no bounded index-artifact catalog
  query, so the UI cannot yet select only eligible indexed Artifacts.
- S-023 persists Query Profile workspaces and owns parsing/compilation. The
  compiler validates a supplied `QueryArtifactBinding`; Query Lab must reuse it
  rather than accept stage/plugin configuration or duplicate planning.
- S-024's `DocumentWorkbenchService.artifact()` and `inspector()` already
  establish the safe manifest/conditional-view projection, locator selection,
  focus return, and narrow responsive drawer. It does not parse query-specific
  Evidence/final-response schemas.
- The static `workbench.js` has a Query Lab route in the shared navigation but
  currently falls through to the placeholder surface. Its existing shell,
  visual tokens, `api()` helper, and browser fixture harness are the intended
  extension points.

## Proposed Approach

### Query Submission, Lifecycle, And Safe API

Add `workbench.query` with frozen request/response models and a
`QueryWorkbenchService`. It reads saved workspaces through the existing Profile
reader, Registry/capability state through server-owned dependencies, and
Run/Artifact facts through existing trace services. Keep a process-local
`QueryJobCoordinator` mapping a submitted query Run ID to its cancellation
event/task; it contains neither historic queries nor provider payloads.

The browser workflow is deliberately two-step:

1. `GET /api/workbench/query-lab/options` returns bounded saved Query Profile
   summaries and only lineage-eligible `search.index.result/v1` Artifact
   summaries, with no storage locator or raw index/vector content.
2. `POST /api/workbench/query-lab/preflights` accepts a bounded UTF-8 question,
   saved Query Profile ID, and index Artifact ID. The service verifies the
   manifest/schema/eligible content, constructs the binding from the manifest,
   compiles the saved Profile, and returns the selected profile, plan digest,
   ordered resolved stage summaries, compact capability readiness, and selected
   external-generation disclosure. It retains an opaque, TTL-limited,
   single-use preflight record only after all validation succeeds.
3. `POST /api/workbench/query-lab/preflights/{token}/runs` requires external
   acknowledgement only when the returned resolved plan declares an external
   generation capability. It revalidates/recompiles immediately, consumes the
   token, starts the engine, and returns `202` with the immutable Run ID and
   digest. Unknown, expired, consumed, or changed preflights return one safe
   workbench problem code; no Run is created before confirmed submission.
4. `GET /api/workbench/query-runs/{run_id}` returns the bounded projection;
   `POST /api/workbench/query-runs/{run_id}/stop` only signals an active task
   owned by this process, otherwise returns `QUERY_STOP_UNAVAILABLE`. There is
   no generic retry or mutation endpoint. A new submission always compiles a
   new resolved plan and creates a new Run.

Refactor the S-015 entry point just enough to support this boundary: give
`QueryEngine` a `submit`/creation callback path that creates the query Run,
publishes the bounded question as an `opaque.bytes/v1` input Artifact in a
recorded internal `query.input` stage, then invokes the existing fixed-plan
execution using that Artifact. The question is bounded (for example 1..8 KiB
UTF-8 after trim), belongs to the query Run lineage, and is not copied into the
plan snapshot, trace summary, metrics, safe errors, or a new query-history
model. `execute` remains usable for existing programmatic tests. The source
stage is not a user-selectable Profile stage or a Registry escape hatch.

Capability readiness is projected from the resolved selected generation
descriptor(s), not inferred by the client from Plugin IDs. The response names
only safe capability/state/code facts and states that question/Evidence content
may be sent to the selected external provider. Empty external stages means no
selected stage is externally backed, not a general offline, privacy, or data
residency assertion. Submission may start a plan whose configured provider is
unavailable so S-015 can persist its authoritative safe `FAILED` final result;
the UI must not substitute an answer or run a browser-side fallback.

### Trace, Evidence, And Final Projection

`QueryWorkbenchService.run()` first verifies the Run is `EngineKind.QUERY`,
then reads its plan and ordered attempts. It maps each recorded stage to a
safe row containing actual timing, plugin identity resolved from the frozen
plan, inputs/outputs, bounded metrics/quality signals, and `SafeError`. It
does not derive unattempted stages or silently relabel execution results.

It resolves query artifacts only through `ArtifactService` and validates the
schema before parsing:

- each retrieval candidate Artifact becomes a separate retriever tab keyed by
  its recorded stage ID; fusion and rerank candidate artifacts retain their
  own tabs/rows and contributor attribution;
- `EvidenceSet/v1` yields Evidence item citation key, excerpt, document/chunk
  identity, exact locators, contributor IDs/safe scores, hierarchy/table facts,
  shortage, and every context decision/reason. Scores are emitted only where
  stored and bounded by their typed contract;
- `GeneratedAnswer/v1` and `VerificationResult/v1` are trace details only;
  their safe attempt/outcome/failure/citation facts support the repairing and
  verification-failed presentations;
- `FinalResponse/v1` is the single authoritative result projection. Answer and
  citation controls are returned only for `ANSWERED` after revalidating its
  contract and its Evidence binding. All other states expose only the stored
  safe action and relevant bounded trace detail.

Malformed, missing, lineage-ineligible, or unexpected artifacts produce a
schema-specific safe unavailable panel. They never cause a client-built answer
or a replacement candidate set. The existing S-024 artifact endpoint/inspector
remains the single source inspector: Query Lab opens it using the source
Artifact where available and passes the Evidence locator/stable target through
the existing selection state (or a small additive query parameter/event
contract). A citation click therefore highlights the exact returned source
locator; it does not fabricate a PDF/document preview or add raw vectors.

### Query Lab UI

Extend `workbench.js`, `workbench.css`, and the existing static fixture server
instead of adding a frontend build system. The route renders simplified-Chinese
controls for question, saved Query Profile, eligible index Artifact, resolved
plan/capability disclosure, submit, and server-authorized cancellation. It
polls only the query Run projection while active, stops polling on terminal or
safe fetch failure, and preserves the last valid projection with a retry-read
command.

At desktop widths the Query Lab uses a stable three-part work surface:

- a compact control and stage-trace pane, including per-retriever/fusion/rerank
  tabs and real stage timing;
- an Evidence/decision pane, with citation-key controls and explicit inclusion,
  exclusion, shortage, contributor, and rationale facts;
- a final-result pane whose terminal-state band is visually distinct from
  verification/repair trace details.

Below 900 px, controls and final result stack while dense candidate/Evidence
tables use labelled scoped horizontal scrolling; source inspection uses the
already-adopted modal drawer. Preserve the shell's focus trap, Escape close,
focus return, visible focus/disabled states, zero-radius controls, ruled light
surface, and teal/blue/amber/red semantic statuses. There are no prototype
scenario switches, synthetic scores/models, chat transcript, raw vector UI,
floating-card sections, or client-side retrieval/verification.

## Relevant Impacts

- **API/data:** Add bounded Query Lab option, preflight, submit, Run-read, and
  Stop contracts plus a safe query trace/artifact projection. Add a bounded
  eligible-index repository read. Question input is a traceable existing generic
  Artifact, not a new durable query/history table or migration.
- **Security:** Reject empty/oversized/non-UTF-8 question input and never put
  it in plans, URLs, logs, metrics, safe errors, or browser fixture data beyond
  the entered control. Client projections exclude credentials, provider URLs/
  bodies, raw prompts, storage locators, arbitrary execution configuration,
  and embeddings. Native DOM rendering uses text nodes rather than `innerHTML`.
- **Observability:** Persisted plan digest, real attempts/timing, selected
  capabilities, safe failures, Evidence/context decisions, verification/repair
  outcomes, final state, and Artifact lineage are inspectable. The coordinator
  only governs active cancellation and does not overwrite trace evidence.
- **Compatibility:** Preserve S-015's fixed compiled-plan execution/final
  state authority, S-023 Profile ownership, S-024 inspector behavior, and
  S-022 shell routes. Existing programmatic `QueryEngine.execute` callers and
  engine fixtures remain supported.

## Alternatives And Risks

- Accepting a raw Profile document, Plugin ID, plan JSON, filesystem path, or
  arbitrary index payload from Query Lab was rejected because it bypasses
  S-023 compilation, Registry allowlisting, and immutable Artifact binding.
- One combined candidate table was rejected because it would erase the required
  retrieval/fusion/rerank/context provenance. Separate panels can be empty when
  an optional stage was not in the resolved plan.
- Treating repair or verification labels as product final states was rejected;
  the S-015 `FinalResponse` contract remains authoritative.
- Persisting a generic cancel lease was rejected. Like S-024 ingestion Stop,
  process-local cancellation cannot survive restart and must be shown only when
  actually owned.
- Query input publication introduces an internal source-stage extension to the
  engine. It must be tested for lineage and safe metadata carefully so it does
  not turn trace plans into a query-content store.

## Test Strategy

- Add Query Lab contract/service/API tests for Profile/index eligibility,
  manifest/digest/schema rejection, question bounds, server compilation,
  preflight expiry/single-use, disclosure acknowledgement, receipt/run
  identity, active/local Stop, restart/unowned Stop, and no manual retry.
- Add Query Engine tests for the new input-materialization path: one bounded
  question Artifact, no question in the plan snapshot/metadata, correct parent
  lineage, callback receipt before completion, cancellation, and unchanged
  existing `execute` behavior.
- Build typed fixtures for factual, table, hierarchy, ambiguous, unanswerable,
  provider failure, verification failure, repair success, and repair exhaustion.
  Assert exact candidate separation, Evidence fields/decisions, source locator
  identity, safe unavailable artifacts, final-state invariants, and absence of
  an answer outside `ANSWERED`.
- Extend static browser fixtures with API-backed Query Lab states. Assert
  capability disclosure/disabled submit, run/cancel transitions, candidate
  tabs, Evidence/citation-to-inspector synchronization, focus/Escape return,
  semantic labels, and no synthetic fallback. Capture deterministic screenshots
  at 1440 x 900 and 644 x 900 and assert document overflow/box overlap is
  absent for long question/Evidence content.
- Run focused query-engine, generation, evidence, workbench, Artifact
  inspector, and browser tests followed by the full regression suite. Docker
  lifecycle evidence remains subject to the existing Compose startup limitation.

## Implementation Checklist

- [ ] Add Query Lab contracts/service/coordinator, bounded eligible-index read,
  and FastAPI routes composed from existing Profile/Registry/trace services.
- [ ] Extend QueryEngine with safe Run creation/question materialization and
  active-task receipt support without changing fixed plan/repair semantics.
- [ ] Implement safe query Run, candidate, Evidence, verification, and final
  projections; reuse the S-024 Artifact inspector/source synchronization.
- [ ] Replace the Query Lab placeholder with responsive native-DOM controls,
  trace/Evidence/result panes, polling, disclosure, and accessible interactions.
- [ ] Add service/API/engine/browser/visual coverage and run focused plus full
  regression suites.

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-025 `story-pipeline` invocation on 2026-09-13; no separate
product decision is required.

## Change History

- **2026-09-13:** Created just-in-time design from confirmed S-025, exact
  adopted UI anchors, and delivered query/workbench dependency contracts.
