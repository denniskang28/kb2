# Story Design: S-004 - Ingestion Profile Compilation And Resolution

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-004-ingestion-profile-compilation-and-resolution.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-11; pipeline delivery
  started 2026-09-11.
- **Material Decisions Requiring Approval:** None. The pipeline invocation
  authorizes the bounded Profile syntax and compiler interfaces below; they do
  not change the confirmed Profile or Plugin allowlist contract.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | `ProfileParser` accepts only bounded JSON or `yaml.safe_load` data and produces immutable `ProfileSet` contracts. `ProfileCompiler` resolves each Profile's fixed six axes, defaulted settings, Registry descriptors, named port bindings, and fallback chain into canonical JSON. It uses the existing `trace.service.plan_digest` for a SHA-256 plan identity. | Contract fixtures compile equivalent JSON and YAML forms plus reordered mappings, then assert byte-identical canonical plans and digests. A complete six-axis fixture asserts every resolved stage is typed and immutable. |
| 2 | Strict Pydantic contracts and semantic validation reject unsafe fields/content, unknown or unavailable Plugins, malformed config, malformed ports, cycles, missing bindings, schema mismatch, unsupported condition AST, forward quality-signal reads, and excessive bounds before a plan is emitted. Failures normalize to stable `ProfileError` codes with bounded JSON-pointer-like field locations. | Parameterized contract matrix asserts one safe error code/location per invalid fixture and proves no Registry factory or Runner invocation occurs. |
| 3 | `ProfileResolver` applies explicit Profile ID, then exact document-class rule, then ordered preflight rules, then `default_profile_id`. The returned `ResolutionRecord` contains candidate profile IDs, every rule evaluated, allowlisted observable values, match outcomes, and final choice. | Unit/contract precedence table covers each winning tier, ties, no-match default, and trace record ordering without exposing source content. |
| 4 | Conditions are a finite declarative AST over fixed `document.<feature>` values and prior declared `quality.<axis>.<signal>` values. Every expanded stage preserves its ordered candidates, `when` predicate, named bindings, and explicit quality acceptance policy in the plan. | Unit matrices exercise valid feature/signal predicates, rejected unknown/future references, candidate fallback order, and `PASS`/`WARN`/`FAIL` acceptance outcomes. |
| 5 | Plugin descriptor port metadata is generic and Registry-validated. A second compatible test component and only Profile data produce a resolved stage without changes to compiler or resolver dispatch. | Architecture regression registers a synthetic compatible descriptor and compiles it into one axis using no compiler/resolver source branch or fixture-specific lookup. |

## Current Code Findings

S-002 already persists an immutable JSON plan snapshot by canonical SHA-256
digest through `RunService.create_run`, and its `plan_digest` rejects non-JSON
or oversized data. Its Artifact catalog is intentionally closed to
`opaque.bytes/v1`, while Artifact manifests retain producer/configuration
digests and lineage. S-004 should compile only; it must not create a Run or
commit Artifacts.

S-003 provides a process-local allowlisted `PluginRegistry`, immutable
`PluginDescriptor`, strict Pydantic configuration models, `PluginExecutor`,
and registered-versus-runnable inspection. Descriptors currently declare
schema pairs but no named ports; the executor consumes a flat tuple of input
Artifact IDs. The compiler needs named stage contracts to prove bindings, so
S-004 extends descriptor metadata in a backward-compatible manner and leaves
actual invocation for a later execution Story. PyYAML is already pinned, so no
new parser dependency is required.

## Proposed Approach

### Module Boundary And Contracts

Add a focused, pure `kb2_runtime.ingestion_profiles` package:

```text
kb2_runtime/ingestion_profiles/
  contracts.py  # frozen Profile, rule, condition, port, plan, and resolution models
  parser.py     # bounded JSON/YAML bytes/text parser and safe structural checks
  errors.py     # stable ProfileErrorCode and ProfileError(location)
  compiler.py   # Registry-backed semantic validation and canonical plan compilation
  resolver.py   # deterministic Profile selection and recorded rule evaluation
```

The public application boundary is synchronous and side-effect free:

```python
ProfileParser.parse(source: str | bytes, media_type: Literal["application/json", "application/yaml"]) -> ProfileSet
ProfileCompiler(registry).compile(profile_set: ProfileSet) -> CompiledProfileSet
ProfileResolver.resolve(compiled: CompiledProfileSet, request: ResolutionRequest) -> ResolutionRecord
```

No HTTP endpoint, database table, migration, Registry mutation, Runner call,
or Plan execution is introduced. A later Story creates an S-002 ingestion Run
from `ResolvedPlan.canonical_payload` and translates its resolved stages into
S-003 executor calls.

### Declarative Profile Shape

`ProfileSet` is the only accepted top-level document. It has
`schema_version: "v1"`, one bounded `default_profile_id`, a unique bounded
list of `profiles`, optional ordered `document_class_rules`, and optional
ordered `preflight_rules`. JSON and YAML are alternate encodings of exactly
this data model; there is no include, anchor merge, template, environment
interpolation, path reference, or parser-specific behavior.

Each Profile has a stable `profile_id` and exactly these six `axes`, in this
fixed declared order: `extraction`, `structure`, `chunking`, `enrichment`,
`embedding`, and `indexing`. This is a constrained ingestion pipeline, not a
general DAG authoring surface. An axis declares non-empty ordered `candidates`.
Each candidate contains only:

- a registered `plugin_id`;
- a JSON-safe `configuration` validated by that Plugin's registered Pydantic
  configuration model;
- named `inputs`, mapping a descriptor input-port name to either a declared
  document input or an earlier axis output;
- named `outputs`, selecting names from the descriptor output-port contract;
- optional `when` condition; and
- an explicit `accept_quality` tuple limited to `PASS`, `WARN`, and `FAIL`.

The first candidate whose condition matches and whose declared acceptance
policy is satisfied is selected at execution time; later candidates are its
strict fallback order. Compilation does not speculate about runtime signals,
but records the complete candidate chain and acceptance policy in the plan.
Each axis has an explicit terminal behavior: the final candidate's acceptance
policy covers all permitted results or the axis declares `on_exhausted:
"fail"`. Skipping an axis is not permitted because the Story requires all six
component axes; a candidate may use a registered no-op Plugin when that is the
intended declarative behavior.

`document_class_rules` are ordered `(rule_id, document_class, profile_id)`
references. `preflight_rules` are ordered `(rule_id, when, profile_id)`
references. Equal-tier ties are invalid at compile time: duplicate document
class values and a preflight rule sequence with more than one matching rule are
not silently resolved by file ordering. The resolver's rules therefore remain
deterministic and explainable.

### Descriptor Port Extension And Graph Checks

Extend `plugins.contracts.PluginDescriptor` with required, immutable
`input_ports` and `output_ports`: bounded unique name-to-schema-pair mappings,
plus bounded unique `quality_signal_names`. The Registry validates that port
value sets exactly match the existing `input_schemas` and `output_schemas`
respectively, with repeated schemas permitted only when ports have distinct
names. `quality_signal_names` declares the only signals later Profile
conditions may consume. The descriptor retains the existing schema tuples for
S-003 executor compatibility. Existing synthetic bootstrap/test descriptors
gain explicit ports such as `source` and `result` and an empty signal-name set.
No Profile can define a port schema, implementation, factory, runner, path,
command, image, secret, or environment value.

During compilation the compiler obtains every candidate only from
`PluginRegistry.get`; it validates registry availability, Pydantic configuration,
declared input/output port names, and schema equality for each binding. A
document input is a named, typed ingress declared once in the ProfileSet;
an axis binding must target an output from an earlier resolved axis candidate.
The compiler creates an edge for every axis-to-axis binding, then rejects any
forward reference, duplicate producer, unbound required port, incompatible
schema, or cycle. The fixed six-axis order itself rejects reverse edges; the
generic cycle walk remains an invariant check and returns a stable error should
the representation evolve.

The immutable `ResolvedPlan` contains a normalized Profile identity, all six
`ResolvedStage` records in fixed axis order, fully validated config, descriptor
implementation digest, runner, typed named inputs/outputs, ordered candidate
fallbacks, conditions, acceptance policy, and an implementation-independent
canonical payload. Canonical serialization uses sorted keys, compact ASCII
JSON, tuples/lists in declared order, no timestamps, and no source filename.
`plan_digest` computes its digest; the compiler returns both the exact payload
and digest. The payload remains within S-002's 64 KiB snapshot bound, enforced
before return.

### Conditions And Resolution Evidence

Conditions are Pydantic-discriminated nodes, not expression strings. The only
nodes are bounded `all`, `any`, `not`, and comparisons `eq`, `in`, `gte`, and
`lte`; a condition has at most 32 nodes and depth 6. Comparison operands are
JSON literals and one permitted observable reference:

```text
document.media_type | document.extension | document.byte_size |
document.page_count | document.language_hint | document.has_embedded_text |
document.is_scanned | document.document_class
quality.<earlier-axis>.<declared-signal-name>
```

The compiler rejects unknown references, calls, interpolation-like strings,
and quality references that target the same or a later axis. It also verifies
the referenced quality signal name is declared by the candidate's Plugin
descriptor extension metadata. Resolution requests contain only the bounded
document-feature model, optional explicit Profile ID, and optional explicit
document class. They do not carry source bytes, filesystem paths, provider
payloads, credentials, or arbitrary dictionaries.

`ProfileResolver` evaluates selection only after compilation. It produces a
frozen `ResolutionRecord` with input feature names/values, every considered
candidate/rule in source order, predicate result, selected Profile ID,
selection tier (`explicit`, `document_class`, `preflight`, or `default`), and
the selected plan digest. It does not log raw content or configuration values.
Its precedence is exact: a valid explicit Profile wins; otherwise a matching
document-class rule wins; otherwise exactly one matching preflight rule wins;
otherwise the configured default wins. An unknown explicit Profile or rule
target is a field-addressable resolution failure, never a fallback.

### Safety, Diagnostics, And Compatibility

Parser input is limited to 64 KiB of UTF-8 text and rejects YAML aliases,
tags, duplicate mappings, non-string keys, non-JSON scalar values, excessive
nested structures, and extra fields. Before model validation, a recursive
allowlist rejects keys or values matching executable/reference vocabulary
(`command`, `script`, `path`, `credential`, `secret`, `environment`,
`entrypoint`, `image`, `mount`, `executable`, `${...}`), and applies the
existing trace sensitive-metadata detector to all declarative strings. This
means a plan can never be safely redacted after digesting: unsafe Profile data
is rejected, rather than changed or persisted.

`ProfileError` exposes only a stable code, a bounded JSON-pointer-like
`location`, and a short allowlisted message. Codes include
`PROFILE_PARSE_INVALID`, `PROFILE_UNSAFE_CONTENT`, `PROFILE_PLUGIN_UNKNOWN`,
`PROFILE_PLUGIN_UNAVAILABLE`, `PROFILE_CONFIGURATION_INVALID`,
`PROFILE_PORT_UNBOUND`, `PROFILE_SCHEMA_INCOMPATIBLE`, `PROFILE_GRAPH_CYCLE`,
`PROFILE_CONDITION_UNSUPPORTED`, and `PROFILE_SELECTION_INVALID`. It includes
no YAML exception, raw Profile fragment, source path, secret, or provider
text. Compiler/resolver logs contain Profile ID, rule ID, digest, stable code,
and timings only.

This is a pure in-memory boundary with no data migration or rollout procedure.
The S-003 descriptor port addition is source-compatible for executor callers
after repository bootstrap registrations are updated; it deliberately makes
new registered components self-describing enough for Profile compilation. S-002
continues to own persistence and canonical plan storage.

## Alternatives And Risks

- Allowing generic DAG nodes or expression strings would make graph and code
  execution validation ambiguous. Fixed axes and an AST keep the required
  composition extensible through Plugins without introducing a workflow engine.
- Inferring port names from the existing unordered schema-pair tuple would be
  insufficient for named input/output validation. Descriptor ports are a small
  generic Registry extension and retain the existing executor schema contract.
- Permitting YAML includes, aliases, or environment substitution would turn a
  declarative Profile into a hidden filesystem/environment reference surface.
  The parser accepts data only.
- A more permissive rule-order tie breaker would be deterministic but obscure
  selection intent. Compile-time ambiguity rejection gives operators a clear
  correction path while preserving the confirmed precedence tiers.

## Test Strategy

Add `tests/contract/test_ingestion_profiles.py` for format parsing, structural
bounds, strict extra-field behavior, canonical compiled snapshots/digests,
all six-axis completion, configuration/default resolution, schema/port/graph
rejection, unsafe-content canaries, safe error locations, and no factory or
Runner activity during compile. Reuse the existing synthetic S-003 Registry
fixture and `opaque.bytes/v1` catalog; no production parser or payload schema
is needed.

Add `tests/unit/test_profile_resolver.py` for explicit/document-class/preflight/
default precedence, all rule-evaluation record fields, no-match and ambiguity
errors, condition feature comparisons, prior-quality references, rejected
unknown/future references, and candidate fallback/acceptance matrices.

Add an architecture regression that registers a second compatible synthetic
Plugin with port metadata and introduces it solely in a Profile fixture. Assert
the compiler resolves it and produces the same generic plan representation
without compiler/resolver dispatch edits. Run existing trace and Plugin
contract suites to confirm plan persistence compatibility and unchanged Runner
semantics.

## Implementation Checklist

- [ ] Add strict Profile/condition/resolved-plan contracts and safe error
  vocabulary under `src/kb2_runtime/ingestion_profiles/`.
- [ ] Implement bounded JSON/YAML parsing and declarative-content safety
  checks.
- [ ] Extend Plugin descriptors/Registry validation with typed named ports and
  update the repository-owned synthetic registrations.
- [ ] Implement compiler semantic validation, fixed-axis graph construction,
  canonical payload generation, and S-002 digest integration.
- [ ] Implement precedence resolver and immutable selection evidence.
- [ ] Add parser/compiler/resolver/security/extension tests and run existing
  Trace and Plugin regressions.

## Open Questions

None. Production Plugin descriptors, source-document Artifact schemas, and
the execution loop remain owned by later confirmed ingestion Stories.

## Approval

Pipeline invocation authorizes this just-in-time technical design. It records
implementation choices only and does not change the confirmed Story contract.

## Change History

- **2026-09-11:** Created for the S-004 Story Pipeline delivery run.
