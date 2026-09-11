# Story Design: S-003 - Plugin Registry And Runners

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-003-plugin-registry-and-runners.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-10; pipeline delivery
  started 2026-09-11.
- **Material Decisions Requiring Approval:** None. The pipeline invocation
  authorizes the local Registry and runner implementation choices recorded
  below; they preserve the confirmed allowlist and common-contract boundary.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | An immutable `PluginDescriptor` and explicit bootstrap registration expose stable revisioned ID, kind, implementation digest, runner type, generated configuration schema, supported input/output Artifact schemas, resource hints, timeout, capability IDs, and separate registration/availability state. Descriptor inspection does not instantiate an implementation. | Contract tests inspect a registered descriptor without calling its factory, then cover valid descriptor fields and available/unavailable states. |
| 2 | `PluginRegistry.register` validates the complete descriptor and its paired trusted implementation binding at bootstrap. It rejects duplicates, malformed stable IDs, unknown runners/capabilities/schemas, incompatible schemas, unsafe schema content, and all executable/container settings before the executor can create an attempt. | Parameterized contract matrix covers each rejection code and verifies no implementation or Runner invocation occurred. |
| 3 | `PluginExecutor` constructs one immutable `StageInvocation`; `InProcessRunner` and `ContainerRunner` implement one `PluginRunner` protocol and normalize into the same `PluginInvocationResult`. The executor commits valid results via S-002 `ArtifactService` under the current Run and Stage attempt. | An integration conformance suite runs the same synthetic transform through both runners and compares output type/revision/digest, metrics, signals, summary, and persisted stage result. |
| 4 | The executor resolves only invocation-declared, eligible Artifact references. Plugins receive a narrow immutable input reader, validated configuration, bounded output writer, absolute deadline, and cancellation token; neither runner receives `Settings`, repository/store objects, host paths, secrets, or a general environment mapping. | Security tests prove undeclared input lookup, forbidden descriptor fields, environment/path access, and configuration injection are rejected or unavailable. |
| 5 | Runner and executor failures map to small stable `TraceErrorCode` values and one sanitized `SafeError`; deadline, cancellation, crash, invalid result, oversized result, and unavailable container runner all terminally fail the attempt without calling `complete_with_outputs`. | Resilience tests assert exactly one terminal failed Stage, bounded/redacted diagnostics, no output links, and no successful downstream Artifact after every negative case. |
| 6 | New implementations are registered through the descriptor/factory binding and use the shared protocol. The synthetic Plugin test fixture adds no Registry dispatch case, runner branch, or executor change. | Architecture test registers a second synthetic Plugin dynamically and invokes it through both standard runners. |
| 7 | Registry inspection reports `registered` independently of runner availability. The existing `runner.container` optional capability is made probeable through the fixed sidecar endpoint, while health/readiness retain S-001 semantics: its absence affects only a Plugin requiring it. | Health/registry integration tests prove an optional unavailable heavy Plugin is listed as registered/unavailable while `/health/live` remains live and default readiness remains controlled by its existing required components. |

## Current Code Findings

S-001 already supplies an allowlisted capability catalog, bounded health output,
and a local Compose topology with no Docker socket mounted into the control
process. `runner.container` is an optional capability but currently has the
`not-configured` probe. The API and worker are read-only containers with the
Artifact volume mounted at the configured `artifact_root`.

S-002 provides immutable Pydantic contract models in `kb2_runtime.trace`,
`RunService.start_attempt` / `fail_attempt`, and
`ArtifactService.complete_with_outputs`. The latter validates every output
against the closed Artifact schema catalog and makes successful Stage output
registration atomic. It already redacts bounded metadata and persists a
`SafeError`, but its error vocabulary contains no Plugin/runner failure codes.
There is no existing Plugin package, dispatch abstraction, plugin metadata
table, execution endpoint, or UI. The Registry can therefore remain an
in-memory, application-owned allowlist at this stage; persistent Registry
editing would contradict the Story's non-goals.

## Proposed Approach

### Domain Boundary And Module Shape

Add a focused `kb2_runtime.plugins` package with typed, internal service
interfaces rather than a generic HTTP execution endpoint:

```text
kb2_runtime/plugins/
  contracts.py      # immutable descriptor, invocation, output/result, availability models
  errors.py         # stable registration/invocation error boundary
  registry.py       # allowlisted descriptor + implementation binding and inspection
  runner.py         # PluginRunner protocol and in-process implementation
  container.py      # fixed sidecar client and container-runner implementation
  executor.py       # S-002 lifecycle, input resolution, result validation/commit
  bootstrap.py      # repository-owned registrations, including synthetic fixture only in tests
  runner_service.py # sidecar request handler using the identical protocol
```

`PluginRegistry` stores an immutable registration object that pairs a
serializable `PluginDescriptor` with a repository-owned implementation factory
and a Pydantic configuration model. The factory and model class are internal
application code, never values parsed from a Profile, request, descriptor
JSON, or environment variable. The descriptor's inspectable configuration
schema is generated from that model at registration, then bounded and checked
for equality with the declared schema. This keeps inspection accurate while
using Pydantic already present through FastAPI for actual resolved-config
validation, without adding an open-ended schema execution engine.

The public application-facing boundary is `PluginExecutor.invoke(...)`, which
takes a Run ID, stage key, registered Plugin ID, resolved declarative config,
and declared Artifact references. Future Profile execution owns choosing those
values; this Story does not parse Profiles. Registry lookup and inspection are
typed Python service methods only. FEAT-005 may later publish read-only API/UI
views over these models.

### Descriptor, Allowlist, And Availability

`PluginDescriptor` is an immutable, extra-forbidden model with these fields:

| Field | Rule |
|---|---|
| `plugin_id` | Stable `kind.name@positive-revision` identifier, unique in the Registry; it is not a filesystem module path. |
| `kind` | Bounded label describing the typed engine stage. |
| `implementation_digest` | Lower-case SHA-256 identity of the reviewed implementation/build content. |
| `runner` | Closed enum: `in_process` or `container`. |
| `configuration_schema` | Bounded JSON-safe schema generated from the paired closed Pydantic config model. No `$ref`, remote URI, command, script, path, credential, environment, image, mount, or executable fields are accepted. |
| `input_schemas`, `output_schemas` | Non-empty, unique `(artifact_type, schema_revision)` pairs, all present in `trace.schemas.SUPPORTED_ARTIFACT_SCHEMAS`; output schemas remain constrained by the current `opaque.bytes/v1` catalog until later Stories extend it. |
| `resource_hints` | Bounded declarative CPU/memory/GPU-class labels and output limits for inspection/scheduling only; never a host resource command. |
| `timeout_seconds` | Positive bounded value, additionally capped by the local runtime maximum. |
| `capabilities` | Unique IDs declared in the loaded S-001 capability catalog. |

It intentionally has no command, entrypoint string, package URI, module path,
image, mount, environment, credential, or host-path field. Container image,
networking, and command are fixed by the repository-owned sidecar deployment,
not supplied per Plugin. Registry registration validates descriptor syntax,
schema compatibility, catalog capabilities, runner availability probe binding,
and the internal factory/config-model pair before adding it. Errors are stable,
safe registration codes such as `PLUGIN_DESCRIPTOR_INVALID`,
`PLUGIN_ID_DUPLICATE`, `PLUGIN_RUNNER_UNSUPPORTED`,
`PLUGIN_SCHEMA_INCOMPATIBLE`, and `PLUGIN_EXECUTABLE_CONFIGURATION_FORBIDDEN`.

Inspection returns an immutable `PluginAvailability` view. `registered=True`
means descriptor validation and allowlisting succeeded. `runnable` additionally
requires every declared capability and its selected Runner to be ready. An
optional heavy Plugin whose sidecar is absent remains registered with a bounded
`RUNNER_UNAVAILABLE` reason; this is not a health failure of the control
process.

### Common Invocation And Result Contract

Use names that avoid collision with S-002's `StageResult` terminal enum:

```text
StageInvocation
  run_id, stage_attempt_id, stage_key
  plugin_id, implementation_digest
  validated_configuration, configuration_digest
  inputs: tuple[ArtifactReference, ...]
  deadline_at, cancellation_token

PluginInvocationResult
  outputs: tuple[PluginOutput, ...]
  summary, metrics, quality_signals

PluginOutput
  artifact_type, schema_revision, content bytes
  bounded summary, metrics, quality_signals
```

All models are frozen, `extra="forbid"`, JSON-safe where serialized, and have
explicit count/byte/text limits. The executor computes the configuration digest
from canonical validated config using S-002's digest convention. It supplies
an immutable declared-input collection and a narrow read-only input resolver
which accepts only one of those reference IDs; there is no generic Artifact
search, repository, store, settings, credential, or environment API in Plugin
context. The resolver reads only eligible S-002 Artifacts and carries their
declared reference alongside bounded content. The executor constructs each
`ArtifactInput` itself, pinning the registered Plugin ID and configuration
digest; a Plugin cannot forge producer identity, choose storage locators, or
attach undeclared parent IDs.

`PluginRunner` is one async protocol:

```python
async def invoke(invocation: StageInvocation, context: PluginContext) -> PluginInvocationResult: ...
```

`InProcessRunner` invokes only its pre-registered factory with that context.
It applies the deadline/cancellation boundary, captures all unexpected
exceptions, and never passes the executor's service objects. This is a trust
boundary, not a security sandbox; only reviewed lightweight implementations
may use it.

`ContainerRunner` serializes precisely the same invocation/result wire model
to a fixed local `plugin-runner` sidecar. The sidecar is built from this
repository's runtime image and runs `runner_service.py`; it dispatches only
the same internal allowlisted implementation bindings installed in that image.
The API/worker neither execute Docker nor receive a Docker socket. The
sidecar accepts a bounded request, no credential/environment forwarding, and
returns only the validated result envelope. Inputs are copied over the runner
protocol solely after the executor resolves the declared references; no host
path or Artifact volume locator crosses the protocol. The sidecar has a
read-only root filesystem, `tmpfs` scratch, no published host port, no secrets,
and no Artifact volume mount. This fixed service is the local-container runner;
it is not a claim of unbounded hostile-code sandboxing.

Add a small container-runner probe for its fixed internal endpoint and update
the catalog entry from `not-configured` to that probe. Keep it optional. The
normal local Compose stack starts the sidecar so registered container Plugins
are runnable on a developer machine; missing/failed sidecar makes only those
Plugins unavailable. Test overlays can deliberately omit or stop it to verify
the unavailable path.

### Executor Lifecycle, Validation, And Failures

`PluginExecutor.invoke` follows this ordered boundary:

1. Look up and validate the registration, then validate resolved config and
   declared input reference schemas before `RunService.start_attempt`; reject
   invalid/unavailable registrations before invocation.
2. Start one S-002 Stage attempt; resolve only declared eligible Artifacts;
   form the invocation deadline and cancellation token.
3. Dispatch through the selected Runner, enforcing descriptor timeout and
   total request/result/output count/output byte limits on both sides.
4. Validate every output against the descriptor's allowed output schemas and
   bounded metadata. Build its `ArtifactInput` with the invocation's parent
   IDs, producer ID, and configuration digest.
5. On success, call `ArtifactService.complete_with_outputs` once. Its existing
   atomic S-002 behavior creates the output manifests and the successful Stage
   result together.
6. On any failure after the attempt starts, call `RunService.fail_attempt`
   exactly once with a sanitized `SafeError`, and re-raise only the stable
   domain error to callers. Do not call output completion on a failure.

Extend the S-002 error vocabulary with Plugin-domain codes such as
`PLUGIN_NOT_REGISTERED`, `PLUGIN_UNAVAILABLE`, `PLUGIN_INVOCATION_TIMEOUT`,
`PLUGIN_INVOCATION_CANCELLED`, `PLUGIN_CRASHED`, `PLUGIN_RESULT_INVALID`, and
`PLUGIN_OUTPUT_LIMIT_EXCEEDED`. They use `validation` or `dependency`
categories, a short allowlisted message, no provider/container exception body,
and retryability only where the bounded runner-unavailable policy permits it.
The executor guards the finalization path so a runner timeout/cancellation/crash
cannot produce a second failure transition. Existing Artifact validation errors
continue to be authored by `ArtifactService` and remain authoritative.

Every completed invocation is inspectable through the persisted S-002 Stage
trace: timing, terminal result, output Artifact references, metrics, quality
signals, bounded summary, or safe error. Registry descriptor/availability
inspection is current-process metadata and does not require a database table
or migration in this Story.

### Synthetic Extension Fixture

Provide a minimal deterministic byte-transform Plugin in test support and
register it with both runner bindings. It consumes `opaque.bytes/v1`, produces
the same schema, and emits stable bounded metric/signal values. A second test
Plugin is added solely by registering its descriptor, config model, and
implementation fixture. Tests must demonstrate no edits to Registry lookup,
Runner protocol, container wire handler, or executor are necessary. This is
the extension proof; it is not a production Parser/OCR/Chunker implementation.

## Relevant Impacts

### Runtime, Data, And Compatibility

No S-002 table change or Alembic migration is needed. Plugin descriptors are
reviewed process-local bootstrap data, while invocation evidence belongs in the
existing Run/Stage/Artifact persistence substrate. Add the fixed unexposed
Compose `plugin-runner` sidecar and its optional capability probe. It uses no
new host port, Docker socket, secret mount, arbitrary package installer, or
per-Plugin command. Existing API and worker readiness remain backward
compatible because `runner.container` is optional.

Later Profiles select descriptor IDs and supply resolved config; later domain
Stories add reviewed Artifact schemas and production Plugins through these
interfaces. They must not add direct executor branches or bypass output
validation. FEAT-005 can consume Registry availability and S-002 traces as
read models without introducing Registry mutation UI.

### Security And Observability

The allowlist is the authoritative implementation-selection boundary. Treat
all descriptor/config/result wire data as untrusted even though current
bootstrap entries are repository owned. Reject unknown fields and executable
configuration before invocation; use fixed serialization limits and bound
container requests. Neither runner receives raw Settings, secret files,
credential strings, unrestricted environment, locators, arbitrary host paths,
or undeclared Artifact content. The sidecar separation protects dependency
conflicts and heavyweight execution but is deliberately not represented as a
general hostile-code sandbox.

Logs and traces include stable Plugin ID, implementation digest, runner type,
Run/attempt IDs, elapsed time, count/byte totals, and allowlisted outcome code.
They exclude configuration values when sensitive, Artifact bytes, locators,
exception text, provider/container bodies, and credentials. Reuse S-002's
metadata redaction at every response boundary.

## Alternatives And Risks

- Running Docker commands from the API container would make per-invocation
  isolation appear simple, but it requires Docker CLI/socket access and turns
  descriptor configuration into a host-execution surface. The fixed sidecar
  preserves the allowlist and current Compose security boundary.
- Treating an in-process child process as the container Runner would make
  contract tests easier but would not meet the distinct local-container
  requirement. Both runners instead share the protocol while executing in
  separate deployment contexts.
- Persisting descriptors now would imply user-editable Registry lifecycle and
  migration obligations without a Story-owned management flow. Explicit
  bootstrap data is sufficient for an allowlisted local runtime.
- The sidecar cannot safely execute arbitrary third-party code merely because
  it is a container. The design limits it to reviewed code installed in the
  repository-built image; stronger sandboxing is expressly out of scope.

## Test Strategy

Add focused contract tests for descriptor shape/immutability/schema generation,
duplicate and invalid registration, capability and runner availability,
configuration validation/canonical digest, closed input/output schema checks,
forbidden executable fields, and descriptor inspection without factory loading.
Use canary strings to assert configuration, diagnostics, logs, result envelopes,
and persisted S-002 errors redact credentials/provider payloads.

Add executor tests with fakes for deterministic valid result, undeclared input,
invalid result/schema, oversized result, timeout, cancellation, crash, and
unavailable runner. For each post-start failure assert one failed Stage trace,
no successful outputs, and no eligible downstream Artifact. Retain all S-002
trace-contract tests unchanged.

Add Docker-backed integration coverage that starts the normal test runtime with
the sidecar, registers the synthetic Plugin, creates an S-002 ingestion Run,
and invokes the identical input/config through in-process and container
Runners. Compare their `PluginInvocationResult` semantics and persisted Stage
traces. A second scenario stops or omits the sidecar and confirms the heavy
Plugin remains registered/unavailable while liveness and default readiness
remain healthy. Run existing S-001 lifecycle/health and S-002 persistence
regressions after focused tests.

## Implementation Checklist

- [ ] Add immutable Plugin contracts, stable failure codes, and strict
  descriptor/config/result limits.
- [ ] Implement Registry bootstrap, duplicate/compatibility validation, and
  registered-versus-runnable inspection.
- [ ] Implement the shared invocation protocol, in-process Runner, and
  executor integration with S-002 lifecycle/output commit services.
- [ ] Add the fixed local `plugin-runner` sidecar, typed wire handler/client,
  optional capability probe, and Compose hardening.
- [ ] Add synthetic cross-runner extension fixtures plus contract, security,
  resilience, Docker integration, and existing regression coverage.

## Open Questions

None. Later Stories own production Plugin payload schemas, Profile selection,
and any stronger production sandboxing requirements.

## Approval

Pipeline invocation authorizes this just-in-time technical design. It records
implementation choices only and does not change the confirmed Story contract.

## Change History

- **2026-09-11:** Created for the S-003 Story Pipeline delivery run.
