# Story Design: S-010 - Ingestion Engine Execution And Validation

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-010-ingestion-engine-execution.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-11; FD-012 correction
  confirmed 2026-09-12.
- **Material Decisions Requiring Approval:** None. FD-012 resolves the
  formerly blocking Profile-plan composition issue. The pipeline invocation
  authorizes the bounded representation and runtime choices below.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Normalize every Profile axis to bounded, ordered sub-stages in the compiled plan. `IngestionEngine` resolves the Profile before creating an `INGESTION` Run, records the exact plan, materializes the typed document source, binds only successful named outputs to later sub-stages, and verifies exact pinned descriptor/port/output contracts. | Integration submits native, scanned, and table-heavy fixtures using explicit and resolver-selected Profiles; assert one pinned plan per Run, typed source/derived lineage, named input order, and no invalid output enters the logical downstream map. |
| 2 | Persist a deterministic stage key for each axis/sub-stage/candidate. Predicate-false candidates are `SKIPPED`; failed, cancelled, drifted, and output-invalid candidates are `FAILED`; a reserved engine signal records accepted or rejected quality selection. | Resilience matrix asserts distinct trace evidence for skips, quality-rejected candidates, selected fallback, retry, cancellation, Plugin failure, and output-validation failure. |
| 3 | Retry once only when the persisted failed attempt is retryable, retaining the same Run, sub-stage candidate, and plan digest. A Registry descriptor that differs from the pinned implementation/configuration/ports fails that Run; a fresh compilation/submission yields a new Run. | Assert retry attempt numbers increase under one stage key and keep its plan digest; changed descriptor/configuration yields a distinct compiled plan and Run. |
| 4 | Supply sanitized native OOXML/hierarchical, scanned bilingual OCR, and table-heavy Canonical profiles. They share registered structure, chunking, enrichment, embedding, projection, and index components while varying declared extraction and structure/chunking configuration. | End-to-end coverage reaches `search.index.result/v1` for all three and retains expected citations, locators, hierarchy/table evidence, Profile selection, and component identity. |
| 5 | A test-only compatible document strategy declares a Plugin and Profile data only, including its typed sub-stage bindings. The generic compiler and engine consume it with no Plugin-ID, document-class, or fixture branch. | Architecture regression registers the synthetic Plugin, compiles the fixture Profile, and runs it end to end without changing orchestration source. |
| 6 | Persist ordered stage inputs and bounded resolver evidence alongside existing stage outputs, timing, metrics, signals, and safe errors. Readback extends `RunTrace` with these records after service restart. | Contract and Docker restart tests create successful and failed Runs, restart the runtime, and assert equivalent inputs, outputs, attempt states, resolver record, metrics/signals, timings, and redacted errors. |

## Current Code Findings

`ingestion_profiles.Axis` currently requires one candidate list per one of the
six fixed axes. Its compiler emits one resolved stage per axis and makes each
axis output available as `axis.output`. The compiler already validates named
ports, configuration, fallback output compatibility, prior-axis quality
conditions, canonical JSON/digests, and fixed forward order. `ProfileResolver`
already supplies the bounded selection record needed for a Run.

The direct dependency Plugins require explicit intermediate transitions:
native and scanned extraction use Parser/OCR then a schema-specific
normalizer before structure, while local indexing uses embedder, search
document projector, then indexer. FD-012 now authorizes these as declared
sub-stages rather than hidden engine dispatch.

`PluginExecutor` owns Runner invocation, cancellation, safe failed attempts,
and atomic Artifact publication. It currently returns only output IDs, accepts
any output tuple whose individual schemas appear in the descriptor, and calls
`RunService.start_attempt` without input IDs. `RunTrace` exposes stage outputs
but not exact inputs or a Profile-resolution record. `ArtifactService` can
materialize a submitted source only inside a started trace attempt.

## Proposed Approach

### Backward-Compatible Profile Plan

Extend `ingestion_profiles.contracts` with a frozen `SubStage` contract:

```text
stage_id: /^[a-z][a-z0-9_.-]{0,47}$/
candidates: 1..16 Candidate values
on_exhausted: "fail" when the last candidate is not quality-total
```

Extend `Axis` with optional bounded `sub_stages` (1..8). Its existing
`candidates` and `on_exhausted` fields stay accepted for backward-compatible
Profile input. Exactly one form is valid: a legacy single candidate list or a
`sub_stages` list. The compiler normalizes legacy input to one sub-stage with
the deterministic ID `main`; this does not alter the six user-facing axes.

The resolved plan keeps top-level `stages` in fixed axis order and replaces
each axis candidate list with an ordered `sub_stages` list:

```json
{
  "axis": "extraction",
  "sub_stages": [
    {"stage_id": "parse", "candidates": ["..."], "on_exhausted": "fail"},
    {"stage_id": "normalize", "candidates": ["..."], "on_exhausted": "fail"}
  ]
}
```

Each candidate retains the existing pinned Plugin ID, implementation digest,
runner, validated configuration, named input/output schemas, predicate, and
quality acceptance. The compiler processes global axis/sub-stage order. New
outputs are available as `axis.stage_id.output_name`; legacy input aliases
remain `axis.output_name` only for legacy one-item axes. Inputs may reference
only `document.*` or earlier global sub-stage outputs. Conditions retain the
legacy `quality.axis.signal` form when that axis has exactly one prior
sub-stage, and use `quality.axis.stage_id.signal` for an exact prior
sub-stage. Ambiguous same-axis aliases and forward/self references are rejected
at compile time. The resolved plan is still canonical JSON and still bounded
by the existing 64 KiB plan snapshot limit.

This is a constrained linear execution representation: it adds neither loops,
fan-out/fan-in authored outside named ports, arbitrary edges, nor runtime
stage generation. Existing single-stage Profile fixtures recompile as a
one-sub-stage plan; their digest may change because the plan representation is
now explicitly expanded, but identical input under the revised compiler has a
stable digest.

### Engine Execution

Add `kb2_runtime.ingestion_engine`:

```text
ingestion_engine/
  contracts.py  # bounded submission, execution receipt, resolver evidence
  engine.py     # source materialization and sequential plan execution
  errors.py     # safe input, plan-drift, output, and exhaustion failures
```

`IngestionEngine.submit` accepts bounded source bytes, an explicit source
schema pair, a `ResolutionRequest`, and a compiled Profile set. It resolves
before calling `RunService.create_run(EngineKind.INGESTION, plan)`. The source
schema must match the plan's declared `document.source` binding; no filename,
path, MIME sniffing, command, credential, or arbitrary configuration is
accepted. The engine writes it through an `ingestion.source` control attempt
via `ArtifactService.complete_with_outputs`, with fixed producer identity
`ingestion.source@1`, a digest of the closed source-schema configuration, and
no parents.

For each axis/sub-stage in plan order, the engine evaluates candidates in
declared order. Its stable stage key is `axis.stage_id.candidate-N`. A false
`when` starts and completes a `SKIPPED` attempt, with inputs and a reserved
engine selection signal. For a matching candidate, the engine obtains the
currently registered descriptor and requires equality with the pinned Plugin
ID, implementation digest, runner, named ports, and schemas. Drift starts a
failed attempt with a safe `PLAN_IMPLEMENTATION_DRIFT` error; it never runs a
new implementation under an old plan digest.

The engine resolves candidate inputs by binding names, then submits IDs in the
pinned descriptor input-port order. `PluginExecutor` receives this order and
records it with the attempt. It gains a backward-compatible
`invoke_with_receipt` method which returns output IDs plus the terminal stage
metrics and quality signals; existing `invoke` continues returning only IDs.
Before commit, the executor requires its output count and ordered schema pairs
to exactly equal `descriptor.output_ports`. The engine rechecks each committed
Artifact manifest against the pinned candidate outputs before exposing it under
the logical `axis.stage_id.output` key.

Candidate quality is the worst emitted stage signal (`FAIL`, then `WARN`, then
`PASS`; no signal is `PASS`). The engine appends a reserved
`engine.candidate-selection` signal to the completed attempt, with a bounded
selection value of `accepted` or `rejected`. A rejected-quality output remains
diagnostic Artifact lineage but never enters the logical output map. The next
declared fallback candidate is then attempted. On a failed invocation, the
engine reads the persisted safe error and retries the same candidate once only
when its `retryable` flag is true; otherwise it proceeds to a declared
fallback. Cancellation terminates the Run with the existing cancellation safe
error. Failure after a candidate's declared `on_exhausted: fail` terminates
the Run. Only when every required final sub-stage has an accepted output does
the engine call `finish_run(..., succeeded=True)`.

`engine.*` is reserved for orchestration signals and cannot be declared by a
Plugin descriptor. Add `PLAN_IMPLEMENTATION_DRIFT` to the closed trace error
vocabulary; it has a bounded validation-category message and no configuration
or source-content details.

### Trace And Migration

Add one forward-only Alembic revision after `0002_artifact_run_trace`:

- `stage_attempt_inputs(stage_attempt_id, ordinal, artifact_id)` captures the
  ordered Artifact references supplied to executed and skipped candidates.
- `ingestion_run_evidence(run_id, resolution_json)` stores the frozen bounded
  resolver snapshot: candidate Profile IDs, rule IDs/tier/match results,
  allowed observables, selected Profile ID/tier, and plan digest. It excludes
  source bytes, paths, Profile source text, credentials, and provider bodies.

Extend `RunService.start_attempt`/`TraceRepository.start_attempt` with an
optional input ID sequence, preserving the existing empty default. Add methods
to record attempt observations after output publication and to persist/read
ingestion evidence. Extend `StageTrace` with ordered `inputs`, and `RunTrace`
with optional typed ingestion evidence. The existing trace redaction boundary
validates every new value before persistence. Non-ingestion callers retain
empty inputs and no ingestion evidence.

## Relevant Impacts

### Data And Compatibility

The Profile source syntax change is additive: legacy Profile data remains
valid and compiles to one `main` sub-stage per axis. The compiled plan shape is
revisioned by its canonical payload and digest rather than a mutable lookup.
Trace changes are additive and use one migration; existing Run and Artifact
rows remain readable. No HTTP endpoint, scheduler, mutable active index,
Profile database, or UI is added.

### Security And Observability

Only Registry-allowlisted descriptors in the pinned plan run. The source is
opaque Artifact content; trace fields contain IDs, digests, schemas, bounded
observables, timings, metrics, quality signals, and safe errors only. The
engine does not retain raw source, provider payloads, filesystem references,
commands, environment values, or credentials in its contracts or diagnostics.

## Alternatives And Risks

- Adding `normalization` and `projection` as axes would expose technical
  implementation detail in the stable six-axis product contract. FD-012's
  bounded sub-stages retain that contract.
- Hiding normalizer/projector calls in the engine would make a pinned plan
  incomplete and prevent Profile-only extension. It is rejected.
- Artifact parent lineage alone cannot explain input order for multi-input,
  skipped, or failed attempts. Explicit input links are necessary for restart
  diagnosis.
- The existing Docker Compose startup stall may block the Docker restart test
  in this environment. In-memory and contract coverage remains required, and
  the Docker regression must run once Compose is available.

## Test Strategy

Extend `tests/contract/test_ingestion_profiles.py` and
`tests/unit/test_profile_resolver.py` for legacy-axis normalization, bounded
sub-stage IDs/counts, canonical expansion/digest stability, valid
parser-normalizer and embedder-projector-indexer chains, named binding order,
same-axis/sub-stage quality references, and rejection of ambiguous aliases,
future bindings, invalid terminal policy, and excessive plans.

Add `tests/contract/test_ingestion_engine.py` for bounded submissions, source
schema mismatch, sensitive-data canaries, exact output-port validation, pinned
descriptor drift, selection signals, retry policy, cancellation, and synthetic
strategy extension. Add `tests/integration/test_ingestion_engine.py` for the
three complete representative Profiles, condition skips, quality rejection and
fallback, retry, failure/exhaustion, and final index eligibility using the
real in-process Registry/Executor with trace/artifact doubles.

Extend trace contracts and `tests/integration/test_trace_persistence.py` for
ordered stage inputs, resolver evidence redaction, and successful/failed
ingestion Run readback after restart. Run the existing Profile, Plugin,
Canonical, Adapter, Structure, Chunking, Indexing, Trace, and full regression
suites.

## Implementation Checklist

- [ ] Add `SubStage`, additive `Axis.sub_stages`, compiler normalization,
  global sub-stage graph validation, quality-reference rules, and compiled-plan
  expansion.
- [ ] Add source submission/evidence contracts and sequential
  `IngestionEngine` execution.
- [ ] Extend executor receipts and exact ordered output validation while
  preserving `PluginExecutor.invoke` compatibility.
- [ ] Add trace input/evidence migration, persistence/readback contracts, and
  post-publication candidate-selection observations.
- [ ] Implement retry, fallback, condition skip, cancellation, drift, output
  validation, and terminal eligibility behavior.
- [ ] Add Profile/compiler, engine, three-document end-to-end, extension,
  resilience, restart, and regression coverage.

## Open Questions

None. FD-012 confirms the only material cross-Story design decision. Fixture
composition and the one-retry bound are implementation choices recorded here.

## Approval

The Story Pipeline invocation authorizes this just-in-time technical design.
It implements the confirmed Story and FD-012 without changing product scope.

## Change History

- **2026-09-12:** Created as blocked after finding the original fixed-axis
  plan could not declare required intermediate Plugins.
- **2026-09-12:** Revised to approved after FD-012 confirmed bounded ordered
  sub-stages within the fixed six component axes.
