# Story Design: S-002 - Artifact, Run, And Trace Substrate

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-002-artifact-run-and-trace-substrate.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-10; pipeline delivery
  started 2026-09-11.
- **Material Decisions Requiring Approval:** None. This pipeline design chooses
  local implementation details that preserve the confirmed immutable-artifact
  and plan-bound-run contract.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | A `RunService` creates UUID-identified runs bound by foreign key to a persisted resolved-plan snapshot identified by a SHA-256 digest. A stage attempt is a separately identified, ordered record under the run; its state, result, timestamps, metrics, signals, and safe error are written through explicit lifecycle transitions. | Contract tests reject an unpersisted plan, invalid lifecycle transitions, and a changed plan digest; integration tests reconstruct the same run and attempts from a fresh database connection. |
| 2 | `ArtifactService.complete_with_outputs` validates typed manifests, commits content into digest-addressed Artifact storage, and atomically records metadata, producer binding, lineage, metrics, quality signals, output links, and the successful Stage result. | Contract matrix covers a valid manifest and each required field; integration tests assert stored bytes, manifest, producer, and output link agree. |
| 3 | Validation checks the supplied SHA-256 against content, confirms storage presence and digest on read, validates the registered schema revision through an allowlisted schema catalog, requires the producing run/stage/plugin/configuration binding, and rejects unknown, self, or duplicate parent lineage. Failed validation produces an allowlisted safe failure and never creates an eligible output link. | Negative contract tests cover digest mismatch, missing file, unsupported type/revision, incomplete producer, invalid parent, and tampered stored bytes. |
| 4 | Artifact bytes live only below the existing Artifact volume. PostgreSQL records locators, digests, byte counts, bounded summaries, structured metrics/signals, and allowlisted safe error codes; it does not store content or raw provider exception/payload data. | Tests inspect serialized records/API representations and logs with canary content, provider payload, and credential values; all must be absent. |
| 5 | `stage_key` plus a one-based, unique `attempt_number` groups retries without collapsing them. Existing attempts and Artifacts are append-only. The run retains the original execution-plan snapshot ID and no update path changes it. | Tests record failure then retry, assert distinct IDs/timing/results/output lineage, and prove update/duplicate attempts cannot replace history or rebind the plan. |
| 6 | Alembic migration `0002_artifact_run_trace` owns all S-002 metadata. Repository reads join persisted manifests, lineage, metrics, signals, and errors; current state is derived from the latest persisted attempt and terminal state is retained. | Docker-backed restart test creates representative evidence, restarts the S-001 stack, and asserts equivalent read models and storage digest validation. |
| 7 | `engine_kind` is a constrained `ingestion`, `query`, or `evaluation` value on Run only. Stage and Artifact contracts remain generic (`stage_key`, typed Artifact type/revision, metrics/signals) with no engine-specific columns. | One parameterized architecture-contract fixture creates a synthetic run for each engine kind using the same persistence/service interfaces and asserts identical trace shape. |

## Current Code Findings

S-001 provides a Python 3.12/FastAPI runtime, async `psycopg`, Alembic, a
PostgreSQL/pgvector service, and the named `artifact_data` volume mounted at
`/var/lib/kb2/artifacts`. Its first migration owns only
`runtime_worker_heartbeat`; it is deliberately not a Run/Stage table. API,
worker, and health probes currently expose no engine domain behavior. The
existing configuration already provides `artifact_root`, secret-file handling,
and safe health-output conventions. S-002 can therefore add a domain package
and a second migration without changing the runtime topology or readiness
contract.

No Canonical Document, Chunk, Evidence, Plugin Registry, Profile compiler, or
UI reference exists. The substrate must consequently validate generic schema
identity and manifests without claiming domain-payload semantics or executing
plugins.

## Proposed Approach

### Domain Boundary And Module Shape

Add a focused `kb2_runtime.trace` package. Its public application-facing
interfaces are typed Python services, repositories, and Pydantic contracts:

```text
kb2_runtime/trace/
  contracts.py      # immutable request/read models and constrained enums
  schemas.py        # allowlisted generic Artifact type/revision catalog
  storage.py        # local content-addressed ArtifactStore
  repositories.py   # transactional PostgreSQL persistence/query operations
  service.py        # Run and Artifact lifecycle/validation boundary
  errors.py         # stable safe failure codes; no provider exception text
```

Future engines call the service boundary to create a plan snapshot and Run,
start/finish an attempt, and commit validated outputs. Future inspection code
uses read-model methods (`get_run_trace`, `get_artifact_manifest`, and
`get_artifact_content` after eligibility validation). S-002 does not expose a
generic write HTTP endpoint: no Profile compiler or authenticated operator
workflow exists yet, and accepting arbitrary JSON through the API would weaken
the typed engine boundary. The same read contracts are suitable for a later
thin inspector endpoint/UI without coupling persistence to FEAT-005.

All models use `extra="forbid"`, finite size limits for summary/error/metric
labels, and JSON-safe primitive values. They must not accept arbitrary Python
objects, provider SDK objects, callable code, shell paths, credentials, or raw
exception text.

### Persistent Model

Migration `0002_artifact_run_trace` creates the following tables with UUID
primary keys, UTC `timestamptz` timestamps, foreign keys, and indexes for the
listed read paths:

| Table | Responsibility | Key constraints |
|---|---|---|
| `execution_plan_snapshots` | Immutable resolved-plan snapshot identity, canonical JSON, digest, and creation time | unique SHA-256 `plan_digest`; insert-only; snapshot content is bounded declarative resolved-plan data, never a Profile path or credentials |
| `runs` | Engine-neutral Run, plan binding, requested/current/terminal state, creation/start/end times | `engine_kind` check (`ingestion`, `query`, `evaluation`); immutable `plan_snapshot_id`; terminal fields set only once |
| `stage_attempts` | One execution attempt, its state/result, timing, bounded summary, and safe error | unique `(run_id, stage_key, attempt_number)`; attempt number >= 1; a terminal attempt cannot transition again |
| `artifacts` | Immutable manifest and storage identity | unique producer-attempt/output binding and immutable producer/configuration fields; content digest is an indexed storage identity, not an Artifact identity; no content/blob column |
| `artifact_lineage` | Ordered parent references | unique child/ordinal and no child equals parent; all parents must be eligible Artifacts |
| `stage_attempt_outputs` | Output Artifact references for a successful attempt | unique attempt/output ordinal; output association is insert-only |
| `run_metrics`, `stage_attempt_metrics`, `artifact_metrics` | Bounded numeric measurements | owner, metric name uniqueness; finite numeric values only |
| `run_quality_signals`, `stage_attempt_quality_signals`, `artifact_quality_signals` | Bounded named signals | owner/name uniqueness; constrained status/value/summary only |

Safe errors are a small structured object persisted on `stage_attempts`:
`code`, `category`, `message`, `retryable`, and optional bounded public detail
keys. Codes are allowlisted (for example `ARTIFACT_DIGEST_MISMATCH`,
`ARTIFACT_CONTENT_MISSING`, `ARTIFACT_SCHEMA_UNSUPPORTED`,
`ARTIFACT_PRODUCER_UNBOUND`, `ARTIFACT_LINEAGE_INVALID`, and
`STAGE_OUTPUT_INVALID`). The storage/repository boundary maps unexpected I/O
and database failures to a generic stable code. It never serializes exception
messages, SQL, DSNs, paths outside the configured artifact root, document
content, provider request/response bodies, or credentials.

The `artifacts` manifest has required `artifact_type`, `schema_revision`,
`content_digest`, `byte_size`, `storage_locator`, `producing_run_id`,
`producing_stage_attempt_id`, `producing_plugin_id`,
`configuration_digest`, bounded summary, and its related parent/metric/signal
rows. `configuration_digest` identifies the resolved plugin configuration that
produced the Artifact; it is not a mutable configuration reference. Artifact
type/revision validation is intentionally a small generic allowlist at this
stage, such as `opaque.bytes/v1` for substrate tests. Later Stories extend the
catalog through reviewed typed contracts rather than passing unconstrained type
strings.

### Artifact Content And Eligibility

The local `ArtifactStore` owns only paths derived from validated lower-case
SHA-256 digests:

```text
<artifact_root>/sha256/<digest-prefix>/<digest>
```

The caller supplies bytes or a bounded stream and the declared digest. The
store writes a private temporary file beneath the same configured volume,
computes SHA-256 while writing, checks byte count and digest, fsyncs, then
publishes with an atomic no-replace operation. A pre-existing destination is
accepted only after its bytes revalidate to the same digest; it is never
overwritten. Directory traversal, arbitrary locators, symlinks escaping the
root, and non-SHA-256 algorithms are rejected.

`complete_with_outputs` performs validation in this order: validate
model/schema and producer binding; validate eligible parents; commit/revalidate
bytes; then use one database transaction to insert the immutable Artifact
manifests, lineage, signals, metrics, output links, and the Stage's successful
terminal result. Content addressing deduplicates identical bytes only; each
production event retains its own Artifact manifest and producer identity. If
metadata persistence fails after the content publish, the digest-addressed file
is harmless unreachable content and must never be treated as eligible; an
explicit later maintenance task may reclaim it, which is outside this Story. No
failed transaction updates an existing Artifact. Read eligibility requires a
successfully committed manifest, its succeeded producing attempt, valid
lineage, and a successful digest revalidation of stored content.

### Run And Stage Lifecycle

Run states are `PENDING`, `RUNNING`, `SUCCEEDED`, and `FAILED`. Stage-attempt
states are `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, and `SKIPPED`; their
terminal result is one of `SUCCEEDED`, `FAILED`, or `SKIPPED`. A terminal run
may not receive a new attempt. Starting an attempt requires a non-terminal run
and writes its start time. Completing it writes an end time and exactly one
terminal result; `complete_with_outputs` makes validation, output links, and a
successful result atomic. A separate completion path permits zero-output
control/validation stages without inventing engine-specific fields.

`stage_key` is an engine-defined stable label scoped to the Run. Retrying the
same logical stage creates the next attempt number and a new ID. A retry retains
the Run's immutable plan snapshot, while its own metrics, timing, safe error,
and outputs remain distinct. The service derives current stage state from the
largest attempt number and derives run current state from the persisted attempt
set, while persisting final Run state/timestamps to make terminal reads simple
and restart-safe.

### Trace Read Models And Observability

`get_run_trace` returns a bounded, deterministic read model ordered by stage
key and attempt number. It includes Run identity/engine/plan digest/state,
stage attempt timing/result/safe error, output Artifact references, metrics,
and signals. `get_artifact_manifest` returns only manifest metadata, ordered
parents, metrics, and signals. Content is intentionally excluded from both.
The content-read method validates eligibility and returns bytes only to a
trusted in-process consumer; API/log serializers never include them.

Structured logs use stable event code, run ID, stage attempt ID, Artifact ID or
digest, and timing only. Log entries must preserve the S-001 redaction policy.
This Story requires no additional health component, service, public port, or
rollout/migration choreography beyond normal Alembic upgrade before worker/API
startup.

## Relevant Impacts

### Data And Migration

Add the second forward Alembic migration after `0001_runtime_heartbeat`. It
creates domain tables and indexes only; no legacy data exists to backfill. The
downgrade drops S-002 tables in foreign-key order and leaves S-001 heartbeat
state untouched. Normal `local-stop` persistence semantics apply, so no
destructive migration/cleanup behavior is added.

### Security

The digest and locator are validated data, not caller-controlled filesystem
instructions. All filesystem operations remain under `Settings.artifact_root`;
temporary files are private and destination files become immutable. Bounded
models and allowlisted error mapping prevent raw source/provider content and
credentials from entering database metadata, traces, API serializers, or logs.
Database operations always use bound parameters.

### Compatibility

S-003 consumes this service as its execution-evidence sink but does not need
to alter the Run/Stage schema. Ingestion, query, and evaluation Stories add
their Artifact schemas to the generic catalog and their domain tables beside,
not inside, this substrate. FEAT-005 can read the stable trace models without
owning a separate persistence representation.

## Alternatives And Risks

- Storing Artifact bytes in PostgreSQL would simplify a transaction but violates
  the required large-content boundary and makes trace reads unnecessarily
  heavy. The named Artifact volume remains the correct local content store.
- Treating each retry as an update to one stage row would hide timing and
  failure evidence. Ordered append-only attempts preserve diagnostic value.
- A generic JSON schema registry would invite engine/domain behavior before its
  Stories are confirmed. The deliberately small reviewed allowlist protects
  typed exchange while retaining an extension point.
- Filesystem and database cannot share one transaction. Content-first publish
  plus metadata transaction leaves only unreachable, content-addressed files on
  persistence failure; they are ineligible by construction and safer than a
  manifest pointing at nonexistent bytes.

## Test Strategy

Add contract tests for Pydantic contracts, enum/lifecycle transitions,
plan-binding immutability, artifact manifest fields, schema catalog rejection,
digest/byte/locator validation, valid and invalid lineage, retry history,
bounded summaries, and canary redaction. Tests use a temporary Artifact root
and repository fakes or a disposable PostgreSQL connection only where actual
constraints must be verified.

Add focused PostgreSQL integration coverage through the existing Docker
runtime: migrate to head; create synthetic ingestion/query/evaluation Runs;
persist attempts and Artifact lineage; stop/start the scoped runtime; reconnect
and compare the trace/manifests; then tamper/remove content to prove it becomes
ineligible with a safe code. Run existing S-001 contract and lifecycle suites
unchanged to establish no readiness/lifecycle regression.

## Implementation Checklist

- [ ] Add immutable contracts, schema catalog, safe error vocabulary, and
  bounded trace read models under `src/kb2_runtime/trace/`.
- [ ] Add content-addressed local Artifact storage with atomic publish and
  read-time digest validation.
- [ ] Add repositories and migration `0002_artifact_run_trace` with foreign
  keys, constraints, and read-path indexes.
- [ ] Implement Run/Stage lifecycle and Artifact output-commit service methods.
- [ ] Add contract and Docker-backed restart/validation/redaction tests.
- [ ] Run focused tests plus existing contract and integration regression suites.

## Open Questions

None. Artifact payload schemas beyond the generic substrate test type remain
explicitly owned by later confirmed Stories.

## Approval

Pipeline invocation authorizes this just-in-time technical design. It records
implementation choices only and does not change the confirmed Story contract.

## Change History

- **2026-09-11:** Created for the S-002 Story Pipeline delivery run.
