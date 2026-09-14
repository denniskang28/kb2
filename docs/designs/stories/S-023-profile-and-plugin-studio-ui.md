# Story Design: S-023 - Profile And Plugin Studio UI

## Status

Approved for Story Pipeline development.

## Story Contract Snapshot

- Story: `S-023`, confirmed 2026-09-11.
- Sources checked: confirmed Story; `REQ-017`; `DES-002` and `DES-003`;
  `FD-001`, `FD-002`, and `FD-005`; UI-006, UI-007, and UI-013; and the
  delivered S-003, S-004, S-011, and S-022 contracts, code, and tests.
- Material decisions requiring approval: None. The `story-pipeline` invocation
  authorizes the bounded API, saved-working-configuration, and dependency-free
  browser implementation below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Keep one canonical JSON-safe Profile document in browser state. Form controls are projections of that value; YAML is parsed through the engine parser and re-emitted from the canonical value. The server returns the normalized document and all diagnostics after each validate/compile request. | API/component tests round-trip representative ingestion and query Profiles through form to YAML to form, including sub-stages, candidate fallbacks, conditions, and typed diagnostics. |
| 2 | Project actual `PluginDescriptor` registrations through a read-only Registry API. The editor derives stage kinds, named ports, compatible source choices, and JSON-schema fields from that projection; it never contains a Plugin allowlist, schema, or compatibility algorithm. | Service tests prove only registered compatible descriptors/options are returned; browser tests cover schema fields, incompatible-selection rejection, and accessible move actions. |
| 3 | Validate and compile on the server with `ProfileParser`/`ProfileCompiler` or `QueryProfileParser`/`QueryProfileCompiler`; return only stable field locations, codes, normalized Profile, canonical resolved plan, and digest. Dry run accepts only a successfully compiled saved working Profile plus bounded required engine inputs, then delegates to the existing engine boundary. | Contract tests cover valid result, parser/compiler errors, bad Query Artifact binding, no dry run for invalid/unsaved Profiles, and no browser-side compile. |
| 4 | Add a bounded Registry listing/detail projection from S-003 descriptors and S-002 Runs. It exposes descriptor contracts, current readiness, schema/resource/timeout data, safe examples derived from schema defaults, contract-test Run summaries, and recent Plugin Runs without implementation factories or raw traces. | API/service tests check filter/search/order/bounds, readiness separation, descriptor safety, safe example construction, and omitted raw configuration, errors, paths, credentials, and Artifact data. |
| 5 | Replace only the Studio and Registry placeholders within the S-022 shell. Use stable grid split panes at desktop and a single-column editor/drawer at less than 900 px; native buttons provide move up/down and focus-preserving selection. | Browser keyboard, focus, responsive, and DOM overflow checks at 1440 x 900 and 644 px. |
| 6 | Extend the fixture-backed browser harness with valid, invalid, draft, and Registry-unavailable responses, taking deterministic screenshots in both target viewport classes. | Visual screenshot assertions plus state-specific semantic/focus/disabled checks. |

## Current Code Findings

- S-022 serves dependency-free ES modules/CSS and provides fixed `/workbench/studio`
  and `/workbench/plugins` placeholders. Its only workbench endpoint is the
  read-only overview projection. The shell already supplies desktop navigation,
  narrow modal-drawer behavior, URL-derived context, and the adopted visual
  tokens; S-023 must preserve those semantics.
- S-003's in-memory `PluginRegistry` has immutable descriptors, generated
  closed configuration schemas, named typed ports, resource hints, timeout,
  implementation digest, capabilities, and `registered` versus `runnable`
  inspection. It exposes no HTTP projection and must not instantiate factories
  for inspection.
- S-004 and S-011 own strict data-only JSON/YAML parsing and deterministic
  compilation. Ingestion compilation requires its six ordered axes; Query
  compilation requires a valid `search.index.result/v1` Artifact binding. Both
  return stable field-addressable errors and resolved plan digests, but neither
  persists source Profiles or offers execution HTTP APIs.
- S-010/S-012--S-015 own executable engine stages. Workbench code must not
  reproduce their execution planning. The only existing bounded persisted
  lifecycle facts are S-002 Runs/Artifacts, queried by the S-022 repository
  projection.

## Proposed Approach

### Server API And Working Profile Store

Add focused `workbench` contracts/services and FastAPI routes beneath
`/api/workbench/`. Keep the overview contract unchanged. Persist the current
working source of each Profile in a small local PostgreSQL table rather than in
browser storage or a filesystem path:

```text
profile_workspaces
  profile_id (bounded Profile identifier, primary key)
  profile_kind (ingestion | query)
  source_document (canonical JSON, max 64 KiB)
  updated_at
```

The table is a mutable working-config store, not a revision, approval,
publication, activation, rollback, or history system. Saving replaces the
current bounded declarative value atomically. Candidate copy creates one new
valid identifier with the copied value and a server-generated `updated_at`;
it does not create a version lineage. Add one Alembic migration and a
repository protocol so API tests use fakes while persistence coverage uses the
local database suite.

The API is explicitly split by responsibility:

| Endpoint | Behavior |
|---|---|
| `GET /api/workbench/profiles?kind=&q=` | Bounded, stable-order summary list of saved working Profiles. |
| `GET /api/workbench/profiles/{profile_id}` | Return one saved canonical document and kind. |
| `PUT /api/workbench/profiles/{profile_id}` | Parse and validate a JSON-safe declarative document, require its body ID/kind to match the path, then atomically save and return it. |
| `POST /api/workbench/profiles/{profile_id}/copy` | Validate a new bounded ID and duplicate the current saved document under it. |
| `POST /api/workbench/profiles/validate` | Parse one unsaved form/YAML document and return normalized document plus stable diagnostics; no mutation. |
| `POST /api/workbench/profiles/compile` | Validate then compile from actual Registry readiness. For Query, require a bounded valid Search Artifact reference; return resolved plan/digest and diagnostics. |
| `POST /api/workbench/profiles/{profile_id}/dry-run` | Reload and compile the saved Profile, reject invalid/missing required execution inputs, then call the existing engine service. It never accepts an arbitrary command, source path, code, credentials, or raw Plugin request. |
| `GET /api/workbench/plugins?kind=&runner=&readiness=&q=` | Return bounded filterable descriptors plus current availability. |
| `GET /api/workbench/plugins/{plugin_id}` | Return the safe complete descriptor projection, schema-derived safe example, contract-test Run summary, and bounded recent related Runs. |

All request/response Pydantic models are frozen/extra-forbidden and cap text,
lists, maps, schemas, documents, diagnostics, and result rows. API errors use
a safe `workbench-problem/v1` code; compiler diagnostics retain only the
existing stable compiler code and JSON-pointer location. Reject query text,
document bytes, provider bodies, filesystem locations, environment values,
commands, scripts, images, mounts, secrets, credentials, executable fields,
unknown document properties, and direct Plugin invocation inputs.

The registry projection is assembled from `bootstrap_registry()` using the
same non-probing health snapshot as the workbench, so Registry readiness is
current but does not make core health depend on optional capability health.
Descriptor details contain ID, kind, runner, named inputs/outputs and schemas,
capabilities, implementation digest, configuration schema, resource hints,
timeout, availability/reason, safe defaults-only example, and bounded
contract-test/recent Run facts. They never expose an implementation factory,
container configuration, source path, arbitrary configuration echo, raw
error, Artifact locator/content, or credentials.

### Editor State And Browser UI

Extend `workbench.js` with two route components while retaining the S-022
shell and native DOM construction. No Node toolchain, editor library, code
editor, JSON-schema evaluator, client-side compiler, or browser persistence is
added.

The Studio has an Ingestion/Query mode switch, searchable saved-profile list,
stable editor toolbar, selected Profile heading, Form/YAML tabs, ordered stage
surface, selected-stage inspector, diagnostics/compile-result panel, and
saved/draft/unavailable state band. The canonical document in memory is the
sole draft. Form changes update it through narrow model adapters; switching to
YAML serializes it deterministically. YAML changes are held as draft text,
then only replace canonical state after `validate` succeeds. Parse or compile
errors retain the last valid editor value and focus/link to their exact field
or YAML location. Save is enabled only after successful validation; compile
may inspect an unsaved valid draft but dry run is disabled until a matching
saved Profile is successfully compiled.

The stage inspector draws all configuration controls from the descriptor's
returned JSON schema: scalar enum/input/number/boolean controls and bounded
object fields only. Unsupported schema features are presented as inspectable
read-only schema, never as an arbitrary JSON/code input. Candidate choices are
filtered from actual named input/output schemas and stage slot constraints;
the server repeats every compatibility check. Conditions and fallbacks use the
closed structures already accepted by the Profile contracts. Add/move/remove
actions are ordinary labelled buttons. `Move up`/`Move down` update declared
order, disable at bounds, preserve selection/focus, and remain available even
if a later enhancement adds pointer reordering.

The Registry route provides search and kind/runner/readiness filters, dense
descriptor rows, status counts based only on returned data, and a detail
inspector. At desktop the list/detail layout is a constrained two-column grid;
at narrow sizes its inspector opens as a labelled modal drawer with the same
focus trap, Escape, overlay close, and focus return behavior as S-022. Detail
sections render contracts, schemas, capability/readiness, resource limits,
safe example, contract-test state, and Run summaries in stable order. An
unavailable descriptor remains selectable and visibly unavailable; it is not
offered as a runnable Profile stage.

Use existing light, compact, ruled, zero-radius styling and semantic colors.
Add only Studio/Registry-specific grid, table, editor, diagnostic, stage, and
inspector rules. At widths below 900 px, panes stack and wide code/schema/table
content scrolls inside its labelled region; the page cannot gain horizontal
overflow. All controls receive visible hover/focus/disabled/error states and
Chinese accessible labels.

### Dry-Run Boundary

Dry run is a real engine operation, not an in-browser simulation. It starts
from the persisted Profile, recompiles using the current Registry and required
typed inputs, and invokes the existing ingestion/query engine with only the
engine's established request contracts. The UI supplies opaque existing IDs
and bounded classifications only. It navigates to the emitted Run context on
success; it does not interpret stage execution, retry failures, or create a
new client-only result model. Before an eligible compile, the control is
disabled with an accessible explanation; validation failure sends no request.

## Relevant Impacts

- **API/data:** Add Profile workspace CRUD/compile/dry-run and Registry
  inspection endpoints plus a single local migration. Existing Profile parser,
  compiler, engine, health, overview, Registry, and Run contracts remain their
  owners and retain their public semantics.
- **Security:** All authored content traverses existing declarative parsers;
  server models enforce strict bounds and no executable/secret/path fields.
  The registry is inspect-only. Client data and logs use safe IDs, diagnostic
  codes/locations, and descriptor metadata only.
- **Observability:** Save/validation/compile/dry-run responses distinguish
  draft validation, Registry unavailability, compilation errors, and engine
  Run IDs. No raw source document, Profile body, provider payload, or stack
  trace is published as a diagnostic.
- **Compatibility:** Existing `/workbench/studio` and `/workbench/plugins`
  URLs become complete workflows without changing shell routing or overview.
  A deployment with no saved Profiles shows intentional empty states; no
  prototype Profile/Plugin data is seeded.

## Alternatives And Risks

- Browser-only saving was rejected because a working save must survive reloads
  and cannot be a hidden file/path configuration surface. A small mutable
  database store supplies local durability without version-management features.
- A generic YAML/code editor was rejected because it would bypass engine-owned
  safety and compatibility contracts. YAML stays a strict declarative input
  validated by the existing parser.
- Client-side JSON-schema validation or compatibility logic was rejected:
  descriptors and Registry availability are runtime facts, and duplicate
  compiler logic could produce a misleading preview.
- Query compilation/dry run needs an actual typed index Artifact. The UI must
  show that required selection state and use the engine's safe error when none
  is eligible; it must not manufacture an index binding.
- Persisting a Profile copy can look like versioning. The UI uses “copy” and
  “working configuration” wording, contains no history/diff/rollback UI, and
  replaces saved state in place.

## Test Strategy

- Add API/service tests for strict body/query validation, saved/list/get/copy
  behavior, deterministic list/filter ordering, atomic replacement, no
  revision/history contract, ingestion and Query parse/compile projection,
  field-addressable diagnostics, valid Query Artifact binding, and dry-run
  eligibility/delegation.
- Add Registry projection tests for descriptor/schema/port serialization,
  filter combinations, non-probing readiness, unavailable-but-registered
  details, safe examples, bounded contract-test/recent-Run selection, and
  redaction of factories, paths, commands, raw errors, Artifact content, and
  credentials.
- Extend browser tests with fixture-backed Studio valid/invalid/draft and
  Registry available/degraded/unavailable/detail responses. Cover keyboard
  route navigation, Form/YAML round-trip, selected-stage focus, move controls,
  save/copy/compile/dry-run enabled states, errors linked to fields, filters,
  inspector drawer focus trap/return, and no `innerHTML` rendering.
- Take deterministic screenshots at 1440 x 900 for Studio valid/invalid/draft
  and Registry detail/unavailable, then at 644 px for Studio and open Registry
  inspector. Assert page `scrollWidth <= innerWidth`, no actionable overlap,
  and reachable labelled controls. Run existing S-003/S-004/S-011/S-022
  contract and regression suites unchanged.

## Implementation Checklist

- [ ] Add frozen workbench Profile/Registry contracts, repository protocol,
  mutable workspace migration, and bounded safe persistence implementation.
- [ ] Wire Profile listing/save/copy/validate/compile/dry-run and Registry
  list/detail routes to existing engine/Registry contracts.
- [ ] Replace Studio and Registry placeholders with native DOM components,
  strict Form/YAML adapters, compatibility-driven stage editing, and inspector
  interactions.
- [ ] Add responsive Studio/Registry styling with accessible reorder/drawer
  behavior and adopted UI-013 states.
- [ ] Add API, persistence, component/accessibility, responsive/overflow, and
  visual-regression coverage; run focused and existing regression suites.

## UI-007 Parity Repair

The 2026-09-14 delivered Registry populated-state repair restored real rows but
left the screen in a permanent list/detail split.  That split contradicts the
adopted UI-007 hierarchy: the Registry is a full-width dense catalog and a
selected Plugin opens a modal detail drawer over the catalog.  The user
confirmed the following bounded correction on 2026-09-14:

- Render the full Registry as a ruled table with Plugin ID, kind, runner,
  accepted and output schemas, capabilities, local availability,
  implementation digest, and contract-test summary.  Extend the existing
  `RegistryPlugin` read model with those descriptor-owned summaries so the
  browser never performs one detail request per row.
- Replace the free-text kind field and secondary runner/readiness controls with
  an `All` plus actual-kind single-select chip set.  Keep server-owned filtering
  and stable ordering; make `q` case-insensitively match Plugin ID, kind, and
  capabilities.  Preserve only `q` and `kind` in the URL so reload and browser
  navigation restore the visible result.
- Open every selected Plugin in the same labelled modal drawer at desktop and
  narrow widths.  The drawer groups typed contracts, configuration schema,
  schema-derived safe configuration, and recent Runs; it traps focus, closes
  with Escape or its scrim/close control, returns focus to the selected row,
  and resets its scroll position for each selection.
- Display only authoritative states.  `runnable` maps to AVAILABLE or
  UNAVAILABLE with its safe reason code.  DEGRADED remains absent until an
  engine-owned readiness contract supplies that state.  Missing contract-test
  or Run history is an explicit empty state and never becomes a synthetic PASS.
- Keep wide-table overflow inside a labelled table region at 1440 x 900 and
  644 x 900.  The page itself must not overflow horizontally; the modal drawer
  must fit the viewport and leave every command reachable.

Verification adds service/API assertions for summary projection, capability
search, kind combinations, and absent run history, plus browser assertions and
captures for the full-width populated table, filtering, modal focus/close, and
desktop/narrow geometry.  No migration, Registry mutation, package operation,
or Profile behavior changes.

## UI-006 Profile Studio Parity Repair (2026-09-15)

The delivered Profile Studio preserves the S-023 safety and engine-authority
boundary, but its two-column list plus fully expanded editor does not preserve
the adopted UI-006 hierarchy. This repair is limited to `/workbench/studio` and
the Profile projections it consumes. It does not change Profile semantics,
Plugin Registry behavior, persistence, the shell, or the adopted reference.

### DOM And Information Architecture

Keep the existing S-022 page shell and replace only the Studio route subtree
with the following stable landmarks. Class names are implementation hooks, not
new product concepts:

```text
main.studio-page
  header.studio-titlebar
    title + subtitle
    tablist "Profile 类型"
      tab "Ingestion"
      tab "Query"
  div.studio-workspace
    aside.studio-profile-pane "工作配置"
      search control + icon-only new/copy-candidate command
      listbox of compact Profile rows
    section.studio-editor-pane "Profile 编辑器"
      toolbar
        Form/YAML mode group
        validate, compile, save, copy, dry-run commands
      div.studio-form-workspace
        section.studio-stage-pane "有序阶段"
          stage list + add command
        section.studio-stage-inspector "所选阶段"
          Plugin, typed ports, schema fields, condition/policy,
          timeout metadata, fallbacks
      section.studio-yaml-workspace
        declarative-only heading + apply-to-form command + textarea
      section.studio-validation-band "验证结果"
        authoritative state, diagnostics with locate actions,
        resolved-plan/digest preview
```

At 1440 x 900, `studio-workspace` is a 280 px Profile pane plus a flexible
editor. Form mode divides the editor into an approximately 290 px stage list
and a flexible inspector, producing the reference's effective three-column
hierarchy. The title-level Ingestion/Query controls use actual `role="tab"`,
`aria-selected`, `aria-controls`, and roving keyboard focus; the Profile kind
is no longer a select inside the list. Form/YAML remains a compact segmented
control in the editor toolbar. Commands stay in the toolbar in the reference
order, using the already pinned Lucide sprite/helper where an icon exists.

Each Profile row shows its real ID, an authoritative state chip, a bounded
stage summary, a short source-document digest, and the time at which the shown
state was checked. The selected row has the three-pixel accent and pressed or
selected semantics used elsewhere in the workbench. The list must not reuse
prototype Profile names, timestamps, summaries, or digests. When those fields
are unavailable, render an explicit unavailable value rather than synthetic
content.

The stage list contains one row per Query stage or one row per normalized
Ingestion sub-stage. An Ingestion row represents its primary candidate; its
remaining ordered candidates are explicit fallback chips in the inspector,
not separate peer stages. The inspector alone renders the selected stage's
compatible Plugin selector and configuration. It shows descriptor-owned named
input/output ports and their schema revisions, required markers and scalar
types from `configurationSchema`, the contract-supported condition/policy,
and descriptor timeout as read-only metadata. It must not expose a writable
timeout when the Profile contract has no timeout field. Query `max_attempts`
and Ingestion `accept_quality`/`on_exhausted` remain their actual contract
controls.

Add, remove, move, and fallback changes operate only on the canonical draft
document. Query stage ordering is bounded by the parser/compiler contract;
Ingestion axis order remains fixed while sub-stage and candidate order may be
edited where the contract permits it. Every structural edit immediately
invalidates prior validation and compilation. The next validate/compile/save
request is the authority on whether the resulting draft is acceptable.

### Client State And Async Authority

Use one route-local state object rather than independent `valid` and `compiled`
booleans:

```text
kind, query, summaries, listState
selectedProfileId, canonicalDocument, savedDocument, savedDocumentDigest
editorMode, yamlDraft, selectedStageKey
draftRevision
validation: idle | pending | valid | invalid | unavailable
compilation: idle | pending | valid | invalid | unavailable
validatedDraftRevision, compiledDraftRevision
validatedDocumentDigest, compiledDocumentDigest, resolvedPlan, planDigest
mutation: idle | saving | copying | dry-running
listEpoch, selectionEpoch, editorEpoch
```

Dirty state is derived by structural comparison of the canonical draft with
the saved canonical snapshot; it is not inferred from control events alone and
does not treat a browser hash as authoritative. Every accepted local edit
increments `draftRevision`. Validation and compilation eligibility is tied to
the request's matching local revision and the server-returned document digest.
Any form/YAML edit clears the matching eligibility, resolved plan, and dry-run
readiness. Loading a saved Profile means `saved`, not implicitly `validated` or
`compiled` in the current session.

List refresh, Profile selection, compatible-Plugin lookup, descriptor detail,
validation, compilation, save, copy, and dry run each use an `AbortController`
or monotonically increasing request epoch. A response may update the DOM only
when its kind, selected Profile, stage key, and draft revision still match the
request snapshot. Changing kind aborts outstanding selection/editor requests,
clears selection, updates the corresponding tab panel, and then loads the new
list. Selecting another Profile while the current draft is dirty requires the
existing in-page confirmation dialog; browser `prompt()` and `confirm()` are
not used.

Form edits mutate a cloned canonical document through narrow adapters. YAML
text remains separate until `validate` succeeds; invalid YAML never replaces
the last canonical document. Switching Form to YAML asks the server to
normalize the current JSON draft and uses returned canonical YAML. Applying
YAML to Form validates the exact YAML text, adopts `normalizedDocument` only on
success, restores the corresponding selected stage when possible, and focuses
the first diagnostic otherwise. Validation and compilation results render in
the fixed bottom band and are never appended after whichever editor mode is
currently visible.

Save is enabled only for a validation result matching the current draft
revision.
Compile may operate on a validated unsaved draft and, for Query, first obtains
the existing typed Search Artifact binding through an in-page dialog. Dry run
is enabled only when the saved document digest and latest successful compiled
document digest match and both results still correspond to the current draft
revision; Query dry run collects the existing question/Search
Artifact fields in the same dialog pattern. The existing
`INGESTION_DRY_RUN_UNSUPPORTED` response is surfaced as an unavailable command,
not hidden or replaced with a simulation.

### Existing API Implications

Keep the current Profile list/get/save/copy/validate/compile/dry-run and
compatible-Plugin routes and their mutation semantics. The repair requires
only bounded response projection additions:

- Extend `WorkspaceProfileSummary` with `stageCount`, `stageSummary`,
  `documentDigest`, `validationState`, `diagnosticCount`, and `checkedAt`.
  `StudioService.list_profiles` derives these server-side from the stored
  declarative document using the existing parser and canonical serialization;
  the repository may hydrate the bounded source document internally but the
  list response never exposes it. `validationState` is parse validation at
  `checkedAt`, not persisted approval or compilation state.
- Add bounded `canonicalYaml` and `documentDigest` fields to successful
  `WorkspaceProfile` and `ProfileValidation` projections. The server emits
  deterministic declarative YAML from the normalized document. The browser
  does not stringify JSON and label it YAML, implement a YAML serializer, or
  calculate an authoritative digest.
- Return descriptor `inputPorts`, `outputPorts`, `configurationSchema`, and
  `timeoutSeconds` from the already existing Plugin detail request used by the
  selected-stage inspector. Compatibility options continue to come only from
  `POST /api/workbench/plugins/compatible`; the client does not derive or cache
  compatibility across draft changes.

The added fields are additive and bounded. No database migration or stored
validation history is introduced. `checkedAt` must therefore be labelled as a
current check, never “last validated”; `documentDigest` is reproducibility
identity, not user-facing version history. Query compilation still requires
the existing `searchArtifact` request member. Diagnostics remain the existing
safe code plus JSON-pointer location. If summary derivation fails for one
stored Profile, return that row with `INVALID` and bounded diagnostics rather
than fail or omit the entire list.

Creating a blank engine-valid Profile requires defaults the current API does
not own, so this repair does not invent a browser template. The plus command
opens the candidate-copy dialog against the selected saved Profile and labels
the operation “复制为候选”; in an empty list it is disabled with an accessible
explanation. A future true blank-Profile workflow requires a separately owned
engine template contract.

### Accessible Interaction And Diagnostics

- Profile rows and stage rows are native buttons within labelled lists. Arrow
  controls are native icon buttons with visible tooltips/accessible names;
  unavailable boundary actions are disabled, and focus stays on the moved row.
- The selected-stage inspector heading is programmatically associated with its
  stage row. Required fields expose a textual required indicator plus native
  `required`; type labels remain visible and errors set `aria-invalid` and
  `aria-describedby` without relying on color.
- Diagnostic locate actions parse only returned JSON-pointer locations. They
  select the matching stage, switch to Form or YAML as applicable, focus the
  exact control when represented, and otherwise focus the inspector or YAML
  error summary. The validation band uses `aria-live="polite"`; request-level
  failures use `role="alert"` without moving focus unexpectedly.
- Copy and dry-run inputs use labelled in-page modal dialogs with focus trap,
  Escape/cancel, initial focus, error summary, and focus return to the invoking
  command. A destructive remove action requires the same in-page confirmation
  pattern. No native prompt is retained.
- Form/YAML and kind tabs support Left/Right, Home, and End. Every hover,
  pressed, focus-visible, disabled, pending, valid, warning/fallback, and error
  state follows UI-013 semantic colors and remains distinguishable by text or
  icon as well as color.

### Responsive Behavior

At widths below 900 px, the page title and kind tabs wrap without changing
document order. `studio-workspace` becomes one column: the Profile pane has an
intrinsic-content height capped at 220 px, then the editor follows immediately.
Form mode also becomes one column with the stage pane above the selected-stage
inspector. Neither pane receives a viewport-derived minimum height that leaves
blank space. The toolbar wraps Form/YAML first and commands into subsequent
rows while retaining source order and minimum 26 px icon-button geometry.

Long Profile/Plugin IDs use ellipsis only where the full value is available by
accessible name/title. YAML, plan preview, and long schema values scroll within
their labelled regions. Parameter rows change from label/control/type columns
to stacked labels below 560 px. Fallback chips wrap; they never force page
overflow. Dialog width is `min(100% - 24px, 640px)` with bounded internal
scroll. At both 1440 x 900 and 644 x 900,
`document.documentElement.scrollWidth <= innerWidth`, all visible controls
have non-zero geometry, and no action overlaps or clips adjacent text.

### Deterministic Visual Regression Plan

Create `tests/visual/baselines/s023/manifest.json` using the same pinned Chrome,
Archivo, locale, media, stabilization, RGBA comparison, channel tolerance 12,
maximum differing-pixel ratio 0.005, immutable-baseline policy, and prototype
archive SHA-256 convention as S-022 and S-024 through S-028. Record fixture
revision `s023-profile-studio-parity-v2`, UI anchors `UI-006` and `UI-013`, and
reviewed SHA-256 values for each PNG. Baselines are reviewed application
screenshots, not direct pixel comparisons against the executable prototype,
because prototype-only data and controls are explicitly excluded.

Capture this minimum matrix at 1440 x 900 and 644 x 900:

| Scenario | Required visible evidence |
|---|---|
| `studio-query-valid` | Query tab, dense Profile rows, selected stage and inspector, typed ports/schema fields, matching successful validation |
| `studio-query-invalid` | Field-addressable compile diagnostic, selected failing stage, disabled save/dry run |
| `studio-query-draft-yaml` | Real declarative YAML, draft state, Apply to Form, fixed validation band |
| `studio-ingestion-fallbacks` | Fixed axes/sub-stage hierarchy, ordered fallback chips, quality/exhaustion policy |
| `studio-unavailable` | Stable page hierarchy and retryable request failure without fabricated Profile facts |

Before every capture, wait for `document.readyState`, `document.fonts.ready`,
the expected fixture request count, no pending Studio state, and two animation
frames. Normalize fixture timestamps, IDs, digests, and Registry descriptors;
disable animation/transition/caret exactly as in the shared capture manifest.
Assertions accompany pixels: correct tab semantics, selected-stage focus,
compatible-only options, schema types and required markers, stale-response
rejection, locate behavior, modal focus/return, action eligibility by matching
digest, no browser prompts, no horizontal page overflow, and non-overlapping
controls. Dynamic timestamps are fixed in fixtures rather than masked so the
entire rendered surface remains regression-covered.

Focused verification covers the additive service/API projections and all five
browser scenarios, then reruns S-003, S-004, S-011, S-022, and existing S-023
contract suites. The older reachability-only Studio screenshots are replaced
by manifest comparisons; Registry baselines and UI-007 behavior remain
unchanged.

### Candidate-Copy Reference Repair

The existing copy endpoint and persistence contract remain unchanged. On a
deep copy of the saved canonical document, `StudioService.copy` must retarget
only formal references whose value exactly equals the source Profile ID:

- always `default_profile_id` and matching `profiles[].profile_id`;
- for an Ingestion Profile, `document_class_rules[].profile_id` and
  `preflight_rules[].profile_id`;
- for a Query Profile, `selection_rules[].profile_id`.

Choose the rule collections from the server-owned `source.kind` through a
fixed allowlist, then pass the transformed document through the existing
validation and save path. Do not recursively replace strings: references to
other Profiles and unrelated nested configuration values remain byte-for-byte
equivalent, including a business field such as `configuration.fields.corpus`
whose value happens to equal the source Profile ID. This repair changes no API,
schema, persistence model, migration, or browser interaction.

Focused contract tests must cover Query selection rules and both Ingestion rule
collections, assert that the original saved document is unchanged, and assert
that unrelated nested equal-valued configuration survives the copy. Existing
duplicate-target rejection and successful API copy behavior remain regression
requirements.

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-023 `story-pipeline` invocation on 2026-09-12; no separate
product decision is required.

The UI-007 parity repair above was explicitly confirmed by the user on
2026-09-14 and is approved for implementation.

The UI-006/UI-013 Profile Studio parity repair above was explicitly confirmed
by the user on 2026-09-15 and is approved for immediate pipeline development.

The candidate-copy reference repair above is approved by the S-023 repair
`story-pipeline` invocation on 2026-09-15; no separate product decision is
required.

## Change History

- **2026-09-12:** Created just-in-time implementation design from confirmed
  S-023, its exact anchors, delivered dependency contracts, and current
  workbench code.
- **2026-09-14:** Added the confirmed full-width Registry table, actual-kind
  filters, capability search, and modal contract-detail parity repair.
- **2026-09-15:** Added the confirmed UI-006/UI-013 Profile Studio parity repair
  covering the three-level editor hierarchy, authoritative async state,
  bounded additive API projections, accessible responsive interactions, and
  deterministic reviewed visual baselines.
- **2026-09-15:** Added the approved candidate-copy repair design for exact
  kind-specific Profile reference retargeting while preserving unrelated
  configuration values.
