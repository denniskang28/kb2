# Story Design: S-011 - Query Profile Compilation

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-011-query-profile-compilation.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-11; pipeline delivery
  started 2026-09-12.
- **Material Decisions Requiring Approval:** None. The pipeline invocation
  authorizes the bounded Query Profile syntax and compiler contracts below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | A pure `QueryProfileParser` and Registry-backed `QueryProfileCompiler` turn strict JSON/YAML data plus one explicit `search.index.result/v1` Artifact reference into immutable, fixed-order resolved plans. Each resolved stage pins descriptor identity, typed named bindings, validated configuration, branch predicate, and bounded repair policy; canonical JSON and `plan_digest` provide identity. | Contract fixtures compile equivalent JSON/YAML and reordered mappings, assert stable ordered payloads/digests, and cover typed bindings, omitted optional stages, declared branches, and bounded repair. |
| 2 | Strict contracts, Registry inspection, graph/order checks, closed condition ASTs, and stable `QueryProfileError` codes reject unavailable or incompatible Plugins, unbound/forward inputs, invalid stage order/cycles, unsafe data, missing Evidence/final validation, and repair bounds outside 1..3. | Parameterized invalid fixtures assert one code and JSON-pointer-like location, while a Registry spy proves compilation never invokes a factory or Runner. |
| 3 | Five source fixtures under `tests/fixtures/query_profiles/` express the FD-007 families using shared stage kinds and Plugin IDs. Fixture-only compatible descriptor registrations make their composition executable as a compiler contract without adding production query behavior. | Architecture regression compiles all five fixtures, asserts their intentional configuration differences, and registers a replacement compatible retriever only in Profile data without compiler dispatch changes. |
| 4 | `QueryProfileResolver` applies explicit Profile ID, then deterministic declared question/document-class rules, then the default. Its frozen `QueryResolutionRecord` identifies the selected plan, evaluated rules, bounded observables, and pinned Search Artifact reference; it has no mutation path. | Unit precedence matrix covers every tier, invalid explicit selection, no-match default, deterministic rule evidence, and unchanged Artifact IDs/manifests. |
| 5 | `QueryArtifactBinding` snapshots the selected indexed Artifact ID, type/revision, content digest, and byte size as the sole `search.index` ingress in canonical plan data. Descriptor/configuration values therefore include resolved Plugin/model/prompt/parameters, and any change to them or the Artifact binding changes the SHA-256 digest. | Digest snapshot tests vary exactly one model/prompt/configuration/Plugin implementation/Search Artifact field at a time and assert a changed identity; equivalent input remains byte-identical. |

## Current Code Findings

`ingestion_profiles` already supplies the appropriate safety precedent: bounded
JSON/YAML parsing, strict frozen Pydantic data, finite declarative conditions,
Registry descriptor and named-port validation, canonical plan JSON, and
field-addressable `ProfileError` diagnostics. It is deliberately constrained
to the six fixed ingestion axes and must not be generalized or altered for
Query work.

`PluginRegistry` has immutable descriptors with implementation digests,
validated closed configuration models, named ports, availability inspection,
and a no-execution compilation path. `trace.service.plan_digest` creates a
bounded canonical SHA-256 snapshot. `ArtifactReference` and the S-009
`search.index.result/v1` contract provide the required immutable indexed input.
No Query Profile package, Query stage Artifact schemas, query Plugin
registrations, or Query Engine currently exists.

## Proposed Approach

### Module Boundary And Public Contracts

Add a separate pure `kb2_runtime.query_profiles` package. It shares no
ingestion `Axis`, candidate, resolver, or execution type; common low-level
helpers may be copied only when their behavior is contract-tested locally.

```text
query_profiles/
  contracts.py  # frozen source, resolution, Artifact-binding, and plan models
  parser.py     # bounded JSON/YAML parsing and declarative-data safety checks
  compiler.py   # Registry and indexed-Artifact compatibility validation
  resolver.py   # deterministic Profile selection and explanation record
  errors.py     # stable QueryProfileErrorCode and safe locations
```

The side-effect-free application boundary is:

```python
QueryProfileParser.parse(source, media_type) -> QueryProfileSet
QueryProfileCompiler(registry).compile(profile_set, search_artifact) -> CompiledQueryProfileSet
QueryProfileResolver.resolve(compiled, request) -> QueryResolutionRecord
```

`search_artifact` is a frozen `QueryArtifactBinding` made from an
`ArtifactReference`; its pair must be exactly `search.index.result/v1` and its
digest and ID are retained in the plan. S-011 does not read Artifact content,
create a Run, query an index, call a model, mutate an Artifact, or expose an
HTTP endpoint. The later Query Engine will confirm the referenced Artifact is
eligible and persist this canonical payload through `RunService.create_run`.

### Bounded Declarative Profile Shape

`QueryProfileSet` accepts only `schema_version: "v1"`, a unique bounded
`default_profile_id`, bounded unique Profiles, and optional ordered selection
rules. A Profile has `profile_id` and an ordered `stages` sequence (maximum
16). A stage has a stable `stage_id`, a `kind`, one registered `plugin_id`, a
closed Plugin `configuration`, required named `inputs`, selected named
`outputs`, and optional `when` predicate. There are no includes, anchors,
templates, environment interpolation, paths, commands, credentials, source
content, executable code, Plugin factories, or user-supplied schemas.

The compiler allows only this slot order, with each slot optional unless noted:

```text
analyze? -> rewrite? -> route? -> retrieve[1..8] -> fuse? -> rerank?
-> context (required) -> generate? -> verify? -> repair? -> abstain?
-> final_state (required)
```

`retrieve` is the sole repeatable slot. Multiple retrievers retain distinct
stage IDs and output bindings for later fusion/attribution; no authored
fan-out, arbitrary DAG node, or hidden stage expansion is accepted. Stage
references may target `query.question` (`opaque.bytes/v1`),
`search.index` (`search.index.result/v1`), or an output of an earlier declared
stage. They cannot target their own or a later stage. All
declared descriptor input ports must be bound exactly once, requested output
ports must equal the descriptor contract, and all pairs must match exactly.

`context` must produce a declared `evidence` output and `final_state` must
consume it, directly or through declared generation/verification/abstention
outputs. This structural requirement is checked by explicit binding lineage,
not Plugin-ID allowlists, so replacement components remain possible. A Profile
that declares `generate` must declare `verify`; final-state validation is
always required even when generation is omitted. A `repair` stage is permitted
only after `verify`, carries `max_attempts` in `[1, 3]`, and can use only the
already-pinned Evidence, generation, and verification outputs. It is compiled
as one linear bounded-loop stage rather than as a graph back-edge. Zero or
missing repair uses no loop; loop-like output references or bounds outside the
range are rejected.

Plugin configuration remains the only source of Plugin-specific model, prompt,
and parameter choices. The Registry validates it against the registered frozen
configuration model; the compiler serializes that validated configuration with
the pinned Plugin ID, implementation digest, runner, ordered ports, condition,
and repair bound. Later generation descriptors must expose bounded model and
prompt identities in their configuration model. The compiler never treats raw
prompt/provider text as an opaque exception to declarative safety rules.

### Selection, Conditions, And Determinism

`QueryResolutionRequest` carries only bounded `question_class`,
`document_class`, `language_hint`, `question_length`, an optional explicit
Profile ID, and boolean structural availability flags. It never contains the
question text, index payload, session history, path, credential, or arbitrary
metadata. Resolution precedence is exact: valid explicit Profile, a unique
question/document-class rule, first unique matching declared conditional rule,
then default. The compiler rejects duplicate class selectors and condition-rule
overlap it cannot prove disjoint, matching the established ingestion resolver
semantics.

Conditions are finite declarative AST values, not expression strings:
`all`, `any`, `not`, `eq`, `in`, `gte`, and `lte`; at most 32 nodes and depth
6. Operands are JSON primitives or the allowlisted observable references.
Stage predicates may also inspect outputs from earlier stages only when the
descriptor declares a matching bounded quality-signal name. Unknown reference,
call, interpolation, non-finite value, same/later-stage quality reference, or
unsafe node is a `CONDITION_UNSUPPORTED` error.

The resolved payload has sorted map keys, compact ASCII JSON, declared list
order, no timestamp/source filename, and the full `search_artifact` binding.
It is passed unchanged to `plan_digest`, retaining the existing 64 KiB limit.
Identical source data, Registry descriptors, and Artifact binding produce the
same plan digest; a selected Plugin implementation, validated configuration
(including model/prompt/parameters), port/schema, or Artifact identity change
produces a different digest. `QueryResolutionRecord` returns a fresh immutable
plan snapshot plus bounded selection evidence and makes no Registry or Artifact
mutation.

### Diagnostics, Fixtures, And Compatibility

The parser keeps the existing Profile parser's 64 KiB UTF-8, duplicate-map,
safe-YAML, depth, non-finite, interpolation, and sensitive/executable-content
defenses. `QueryProfileError` exposes only a stable code, short allowlisted
message, and location capped at 256 characters. Its closed vocabulary includes
`QUERY_PROFILE_PARSE_INVALID`, `QUERY_PROFILE_UNSAFE_CONTENT`,
`QUERY_PROFILE_PLUGIN_UNKNOWN`, `QUERY_PROFILE_PLUGIN_UNAVAILABLE`,
`QUERY_PROFILE_CONFIGURATION_INVALID`, `QUERY_PROFILE_PORT_UNBOUND`,
`QUERY_PROFILE_SCHEMA_INCOMPATIBLE`, `QUERY_PROFILE_STAGE_ORDER_INVALID`,
`QUERY_PROFILE_GRAPH_CYCLE`, `QUERY_PROFILE_CONDITION_UNSUPPORTED`,
`QUERY_PROFILE_FINAL_VALIDATION_MISSING`, `QUERY_PROFILE_REPAIR_UNBOUNDED`,
and `QUERY_PROFILE_SELECTION_INVALID`.

Add five JSON fixtures: `text-hybrid`, `hierarchy-aware`, `table-aware`,
`high-precision-fact`, and `section-summary`. They differ only in declared
shared-stage configuration and bindings: retrieval contributor types, optional
fusion/rerank, context structural/budget settings, and verification/abstention
policies. They do not create separate services or hard-code document content.
Because S-012 through S-015 own executable retrieval, fusion, context, and
generation Plugins, S-011 supplies fixture-only compatible descriptors and
configuration models for compiler coverage rather than premature production
Plugin implementations or Artifact schemas. Their ports use only the existing
`opaque.bytes/v1` and `search.index.result/v1` catalog pairs, while names such
as `evidence` exercise the compiler's binding/lineage rules. Those later
Stories replace the test descriptors with real Registry registrations and
recompile these same Profile sources against their concrete contracts.

## Relevant Impacts

### Data And Compatibility

This adds in-memory Profile/plan contracts and source fixtures only. It does
not modify `ingestion_profiles`, an existing Artifact payload, persistence
schema, migration, Registry behavior, or API. The sole production Artifact
compatibility check is the existing immutable `search.index.result/v1` input.
Future query-stage Artifact contracts are owned by their producing Stories;
the compiler validates them generically from Registry ports once registered.

### Security And Observability

The compiler is Registry-read-only and Artifact-read-only. It refuses all
unsafe declarative content before digesting, preventing a secret or executable
reference from entering a reproducibility snapshot. Selection evidence holds
only Profile/rule IDs, allowed classification observables, selected digest, and
the already-safe Artifact reference fields. Question text, prompts, provider
requests/responses, credentials, vectors, and Search Artifact content are not
logged or persisted by this Story.

## Alternatives And Risks

- Reusing or extending the ingestion six-axis compiler would conflate two
  intentionally different bounded pipeline contracts and introduce regression
  risk for S-004/S-010. A sibling Query package preserves both boundaries.
- A generic DAG with arbitrary loop edges would make final-validation and
  repair bounds unverifiable. Fixed slots, repeatable retrieval only, and a
  dedicated bounded repair representation implement the confirmed model.
- Compiling only a Profile file and adding the Search Artifact at execution
  would make otherwise identical plan digests refer to different corpora. The
  explicit Artifact binding is necessary for AC 5 reproducibility.
- Registering placeholder production retrievers now would blur ownership and
  imply retrieval/generation capability before its contracts exist. Test-only
  descriptors validate Profile composition; later Stories own runnable
  implementations and schemas.

## Test Strategy

Add `tests/contract/test_query_profiles.py` for JSON/YAML equivalence,
canonical payload/digest snapshots, named typed input/output validation,
Registry availability/configuration errors, unsafe-data canaries, fixed slot
ordering, optional stages, branch predicates, required Evidence/final
validation lineage, repair limits, and safe error locations. Use spies to
prove compiler/resolver paths do not construct Plugins or invoke Runners.

Add `tests/unit/test_query_profile_resolver.py` for explicit/class/conditional/
default precedence, rule evidence order, overlap rejection, unsupported
condition references, and Profile selection with no Artifact mutation. Add
five source fixtures plus a fixture Registry of closed compatible descriptors.
An architecture regression adds a compatible synthetic retriever only through
descriptor registration and Profile fixture data, then proves generic compile
output without compiler/resolver changes. Digest tests independently vary the
Artifact reference, descriptor implementation digest, model/prompt config, and
other parameter values. Run existing ingestion Profile, Plugin, Indexing,
Trace, and full regression suites.

## Implementation Checklist

- [ ] Add frozen Query Profile, stage, selection, Artifact-binding, resolved
  plan, and resolver-record contracts under `src/kb2_runtime/query_profiles/`.
- [ ] Implement safe JSON/YAML parsing, field-addressable errors, conditions,
  fixed stage-order/lineage checks, Registry compatibility checks, canonical
  compilation, and deterministic selection.
- [ ] Add five shared-stage baseline Profile fixtures and fixture-only
  compatible query descriptor registrations.
- [ ] Add contract, resolver/unit, digest/change, safety, and extension-path
  coverage; run focused and full regressions.

## Open Questions

None. Query-stage payload schemas, executable Plugins, retrieval algorithms,
and provider adapters remain deliberately owned by S-012 through S-015.

## Approval

The S-011 Story Pipeline invocation authorizes this just-in-time technical
design. It records the bounded compiler choices without changing the confirmed
product contract.

## Change History

- **2026-09-12:** Created for the S-011 Story Pipeline delivery run.
