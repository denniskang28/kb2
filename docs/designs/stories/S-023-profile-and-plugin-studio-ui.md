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

## Open Questions

None. The pipeline may proceed directly to development.

## Approval

Approved by the S-023 `story-pipeline` invocation on 2026-09-12; no separate
product decision is required.

The UI-007 parity repair above was explicitly confirmed by the user on
2026-09-14 and is approved for implementation.

## Change History

- **2026-09-12:** Created just-in-time implementation design from confirmed
  S-023, its exact anchors, delivered dependency contracts, and current
  workbench code.
- **2026-09-14:** Added the confirmed full-width Registry table, actual-kind
  filters, capability search, and modal contract-detail parity repair.
