# S-003: Plugin Registry And Runners

- **Parent Feature:** FEAT-001
- **Status:** Implemented
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** S-001, S-002

## Outcome

Let every engine discover and invoke only registered, contract-compatible local
Plugin implementations through equivalent lightweight and isolated runners,
while making capability availability and every invocation result inspectable.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| DES | `docs/core-design.md#DES-002` | Confirmed 2026-09-10 |
| DES | `docs/core-design.md#DES-003` | Confirmed 2026-09-10 |
| DES | `docs/core-design.md#DES-004` | Confirmed 2026-09-10 |
| DES | `docs/core-design.md#DES-016` | Confirmed 2026-09-10 |
| Feature | `docs/features/FEAT-001-local-experiment-runtime.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- Implementations are registered by stable, revisioned Plugin IDs and declare
  kind, runner, configuration schema, accepted input/output Artifact schemas,
  resource hints, timeout, capabilities, and implementation identity.
  `[DES-003]`
- A runtime invocation can reference only an allowlisted registered Plugin;
  Profiles cannot supply script paths, embedded code, commands, credentials, or
  unrestricted environment access. `[DES-002][DES-003]`
- Trusted lightweight Plugins may run in process; dependency-heavy, conflicting,
  GPU, or model Plugins use an isolated local-container runner. Both runners
  implement one invocation/result contract. `[DES-003]`
- Plugins receive immutable typed Artifact references and return validated
  Artifact manifests plus bounded metrics, quality signals, timing, and safe
  errors rather than provider SDK objects. `[DES-004]`
- Local Plugin availability is capability evidence only and does not prove a
  future Azure adapter or managed provider. `[DES-016]`

## Scope

- Plugin descriptor schema, registration, duplicate/conflict validation,
  lookup, capability discovery, and local availability checks.
- One common invocation/result protocol integrated with S-002 Run, Stage, and
  Artifact identities.
- In-process runner for trusted lightweight implementations.
- Isolated local-container runner for explicitly registered heavy or conflicting
  implementations.
- Deadline, cancellation, bounded outputs, structured failure, and sanitized
  diagnostics at the runner boundary.
- A synthetic contract-test Plugin proving extension without executor changes.

## Non-goals

- Remote marketplace, arbitrary package installation, user-supplied executable
  code, or container-command editing.
- Implementing production Parser, OCR, Chunker, Retriever, model, or metric
  Plugins owned by later Features.
- Profile schema, compilation, resolution, or conditional pipeline execution.
- Azure adapters, production sandboxing claims, or multi-host scheduling.
- Plugin Registry UI.

## Acceptance Criteria

1. A valid descriptor registers one stable Plugin ID and exposes its kind,
   implementation identity, runner, typed schemas, capabilities, resource
   hints, timeout, and current local availability without loading the Plugin to
   inspect large provider objects.
2. Duplicate IDs, invalid descriptors, unsupported runners, incompatible schema
   declarations, or unapproved executable/container configuration are rejected
   before invocation with a safe actionable reason.
3. The same valid synthetic `StageInvocation` contract executes through the
   in-process and isolated-container runners and returns equivalent
   `StageResult` semantics integrated with S-002 identities and Artifacts.
4. A Plugin receives only declared immutable inputs, resolved validated
   configuration, bounded output scope, deadline, and cancellation context; it
   cannot obtain arbitrary credentials, host paths, environment values, or
   undeclared Artifact content through the runner contract.
5. Timeout, cancellation, Plugin crash, invalid output, oversized output, and
   unavailable runner each produce one bounded structured failure and cannot
   register an invalid downstream Artifact as successful.
6. Adding and invoking a new synthetic Plugin requires only its implementation,
   descriptor, and contract tests; it requires no modification to the Registry,
   runner protocol, or common executor source.
7. Health/capability inspection distinguishes a registered Plugin from a
   currently runnable Plugin and does not mark the entire control process dead
   solely because an optional heavy Plugin is unavailable.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1-2 | Descriptor, duplicate, schema, runner, and availability matrix | Contract |
| 3, 6 | Cross-runner synthetic Plugin conformance suite | Integration and architecture |
| 4-5 | Input isolation, timeout, cancellation, crash, size, and invalid-output scenarios | Security and resilience |
| 7 | Registered/available/required capability-health scenarios | Integration |

## Open Questions

None. Exact Plugin packaging, process protocol, container runtime mechanism,
schema-validation library, and isolation controls are material Story-design
choices; the implementation must preserve the common contract and local
developer usability.

## Relationships And Blocks

- Depends on S-001 local runner/runtime availability and S-002 common execution
  evidence.
- Enables FEAT-002 Profile compilation and its first real processing Plugins.
- FEAT-005 owns Registry, descriptor, and invocation inspection UI.

## Change History

- **2026-09-10:** Compiled from confirmed FEAT-001 sources.
- **2026-09-10:** Story boundary confirmed by the user.
- **2026-09-11:** Implemented, independently verified, reviewed, and merged
  into local main through the S-003 Story Pipeline.
