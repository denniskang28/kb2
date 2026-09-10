# S-002: Artifact, Run, And Trace Substrate

- **Parent Feature:** FEAT-001
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-001

## Outcome

Give every engine one persistent, typed, content-safe substrate for immutable
Artifacts and inspectable Run/Stage evidence so later ingestion, query, and
evaluation work can be reproduced and diagnosed without inventing separate
storage or trace models.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-007` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-002` | Confirmed 2026-09-10 |
| DES | `docs/core-design.md#DES-004` | Confirmed 2026-09-10 |
| DES | `docs/core-design.md#DES-008` | Confirmed 2026-09-10 |
| Feature | `docs/features/FEAT-001-local-experiment-runtime.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Every ingestion run exposes stage state, inputs, outputs, metrics, quality
  signals, timing, and actionable failure evidence. The shared substrate must
  support equivalent evidence for later query and evaluation Runs. `[REQ-007]`
- A Run executes a resolved immutable plan snapshot rather than a mutable
  Profile file. `[DES-002]`
- Stages exchange immutable typed Artifact references, not provider SDK objects
  or arbitrary in-memory objects. `[DES-004]`
- Every Artifact identifies its schema revision, content digest, storage
  locator, producing run/stage/plugin/configuration, parent Artifacts, metrics,
  and quality signals. `[DES-004]`
- Large content stays in Artifact storage while stage records and traces retain
  bounded references and summaries. `[DES-004]`
- Stage outputs are validated before downstream use; terminal outcomes,
  retries, structured errors, and timing remain visible. `[DES-008]`
- Internal snapshots, revisions, digests, and lineage are reproducibility
  mechanisms, not user-facing version-management behavior. `[DES-008]`

## Scope

- Common identities and persistent records for Runs, resolved plans, Stage
  attempts/results, Artifact manifests, lineage, metrics, quality signals,
  timing, and structured safe errors.
- Immutable local Artifact storage and digest validation.
- APIs used by engines and future FEAT-005 inspectors to create/read bounded
  Run, Stage, Trace, and Artifact metadata.
- Restart-safe reconstruction of authoritative current and terminal Run/Stage
  state from persisted evidence.

## Non-goals

- Defining Canonical Document, Chunk, Evidence, evaluation-case, or provider-
  native payload schemas owned by later Features.
- General-purpose event sourcing, distributed tracing backend, retention,
  archival, publication history, or user-facing version browsing.
- Rendering Trace or Artifact UI.
- Executing Plugins or compiling Profiles.

## Acceptance Criteria

1. An engine can create a Run bound to one resolved execution-plan snapshot and
   record independently identified Stage attempts, current state, terminal
   result, timing, and structured failure without referring back to mutable
   Profile content.
2. A successful Stage registers only schema-valid immutable output Artifact
   manifests containing the required digest, locator, producer, configuration,
   parent-lineage, metric, and quality-signal fields.
3. Digest mismatch, missing content, incompatible schema metadata, unbound
   producer, or invalid parent lineage prevents an Artifact from becoming an
   eligible downstream input and produces an actionable safe failure.
4. Large Artifact content is stored outside Run/Stage records; APIs and logs
   expose references and bounded summaries without leaking raw provider payloads
   or credentials.
5. Retry attempts remain distinct and traceable under the same resolved plan,
   and no retry can overwrite a prior Artifact or silently make a changed plan
   authoritative.
6. After a normal runtime restart, Run/Stage terminal state, Artifact manifests,
   lineage, metrics, quality signals, and safe errors remain inspectable and
   internally consistent.
7. The common contract can represent synthetic ingestion, query, and evaluation
   Runs without adding engine-specific state fields to the substrate.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1, 5-6 | Run/stage lifecycle, retry, and restart scenarios | Integration |
| 2-4 | Artifact manifest/schema/digest/lineage validation matrix | Contract and security |
| 7 | Synthetic three-engine fixture compatibility | Architecture contract |

## Open Questions

None. Physical database tables, Artifact storage implementation, transaction
boundaries, and lifecycle enumeration are Story-design choices; they may not
weaken immutability, validation, or engine neutrality.

## Relationships And Blocks

- Depends on S-001 local storage and runtime boundaries.
- Enables S-003 Plugin execution evidence and every later FEAT-002 through
  FEAT-004 engine Story.
- FEAT-005 owns all visual inspection behavior.

## Change History

- **2026-09-10:** Compiled from confirmed FEAT-001 sources.
- **2026-09-10:** Story boundary confirmed by the user.
