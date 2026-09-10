# Story Design: S-001 - Local Runtime And Readiness

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-001-local-runtime-and-readiness.md`
- **Confirmed Version Or Date:** Story confirmed 2026-09-10; delivery started
  on `feature/s-001-local-runtime-and-readiness`. The user confirmed the
  external DeepSeek provider amendment on 2026-09-11.
- **Material Decisions Requiring Approval:** The 2026-09-11 user decision
  replaces the inherited local-generation-model constraint with an optional
  external DeepSeek generation provider. The decision is approved and its
  upstream contract anchors were synchronized on 2026-09-11 as listed below.

## Contract Amendment And Required Synchronization

The user confirmed that Lite will use DeepSeek's official OpenAI-compatible
API at `https://api.deepseek.com` rather than Ollama. The current generation
models are `deepseek-v4-flash` for `generation.default` and
`deepseek-v4-pro` for the optional `generation.high_precision` capability.
Neither capability is part of core local readiness, and no DeepSeek key is
required to start or operate the core local stack.

This explicitly supersedes the previously inherited claim that representative
generation models run locally. The coordinator synchronized these authoritative
anchors before amended implementation began:

- `docs/prd.md#REQ-001`: replace the representative-model-locality requirement
  with a local core stack plus optional external model providers.
- `docs/core-design.md#DES-016`: change the first-runtime requirement from a
  local model provider to a provider-neutral model boundary that may select an
  external provider while local storage and processing remain local-first.
- `docs/features/FEAT-001-local-experiment-runtime.md`, under **Dependencies
  And Risks**: replace the local-model resource statement with explicit
  external-provider configuration and availability semantics.
- `docs/stories/S-001-local-runtime-and-readiness.md`, in **Outcome**,
  **Inherited Requirements And Constraints**, acceptance criterion 1, and
  **Open Questions**: remove the representative-local-provider/model-runtime
  wording and adopt optional external generation with no-key core readiness.

This was a contract synchronization action, not an unresolved product choice.
The listed anchors now reflect the confirmed amendment.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Under the approved 2026-09-11 amendment, `make local-up` invokes one repository-owned runtime CLI that generates ignored local database-secret material, builds the application image, starts the fixed development Compose project, and waits for API, worker, PostgreSQL with pgvector, and persistent Artifact storage. It does not start or download a local model and makes no DeepSeek call. The core stack reaches ready without a DeepSeek key. | From a clean checkout with only Docker, Compose, Make, and Python 3 available, run `make local-up` with no DeepSeek key and assert every core component is ready, both generation capabilities and `embedding.default` are `not_configured`, and no request is made to DeepSeek or Azure. |
| 2 | `make local-health` calls the runtime CLI, which requests a structured health report and prints one sanitized row per component and capability. Required unavailable entries make the CLI exit nonzero. Probes map internal failures to stable codes and never return exception text, connection strings, document data, or provider response bodies. | Contract tests cover schema, status codes, stable error codes, and redaction. Integration tests stop each required dependency in turn and assert a nonzero command result while all expected component/capability rows remain present. |
| 3 | API liveness is process-only. Default readiness checks only core local infrastructure and worker heartbeat. Generation and embedding readiness are separate experiment capabilities. Without a key, both DeepSeek generation capabilities are `not_configured`; with a key but no explicit generation requirement, they are `not_probed`. Only a request whose `require` set contains `generation.default` or `generation.high_precision` may make one minimal non-generating `/models` probe. Requiring either without a key produces HTTP 503 and a nonzero CLI result. | Contract and integration matrix covers: live but database unavailable; core ready with no key; plain capabilities/`make local-health` with a key but zero external requests; required generation not ready with no key; configured DeepSeek fixture with and without each model; and recovery after provider unavailability. Assert no generation request is issued by health logic. |
| 4 | The CLI always supplies an explicit Compose project name. `make local-stop` runs scoped `down` without volume removal. Named PostgreSQL and Artifact volumes persist; there is no model volume. `make local-clean` is a distinct command requiring an explicit confirmation token and removes only the resolved project volumes. | Store non-sensitive sentinel database and Artifact values, stop and restart, then verify both remain. Start a second Compose project and prove stop/clean of the test target does not affect it. Verify cleanup removes only target volumes. |
| 5 | Committed configuration contains provider identifiers, the fixed official DeepSeek base URL, model IDs, and non-secret defaults only. Startup creates the database password and an empty DeepSeek-key file under `.runtime/<project>/secrets/`; both are ignored, mode `0600`, mounted as Compose secrets, and passed by file reference. A user-provided DeepSeek key may only be written through that file path. Local and production environments reject any endpoint other than `https://api.deepseek.com`; only the exact test environment may use the exact fixture URL. Configuration summaries expose only environment, provider, capability, and model IDs. | Static secret-pattern and tracked-file tests, file-mode assertions, trusted-endpoint validation, redirect/proxy rejection, `.gitignore` assertions, image config/history inspection, and canary-key redaction tests over process arguments, container inspection, health output, logs, and generated integration evidence. |
| 6 | The runtime CLI accepts explicit project, environment, Compose overlay, state-directory, and timeout arguments. The integration fixture invokes that same `up`, `health`, `stop`, and `clean` path with a unique project name and disposable state. A deterministic OpenAI-compatible fixture is used only to test optional DeepSeek `/models` probe behavior; the no-key core path has no external-provider dependency. Cleanup runs in `finally` and verifies no target containers, networks, volumes, or secret files remain. | A single isolated integration suite exercises no-key success, configured-provider capability success, restart/persistence, optional capability absence, induced required dependency failure, recovery, scoped shutdown, and deterministic cleanup. It records only sanitized command summaries. |

## Current Code Findings

The repository currently contains planning Harness files, validation scripts,
and a Makefile with only `harness-check`. There is no application package,
container topology, dependency manifest, migration baseline, health contract,
or integration-test framework to preserve. The design therefore establishes a
small runtime skeleton for later Stories without implementing Artifact, Run,
Plugin, Ingestion, Query, or Evaluation domain behavior.

The active branch is `feature/s-001-local-runtime-and-readiness`, based on the
initial Harness commit. Existing Story Pipeline edits to the Story, current
state, Feature, and run log are owned by the parent pipeline and are not part of
this design's edit scope.

## Proposed Approach

### Runtime Topology

Use Docker Compose v2 as the only service orchestrator and Python 3.12 for the
thin control process and worker skeleton. The default local project contains:

| Service / Store | Implementation | Story-owned responsibility |
|---|---|---|
| `api` | FastAPI application from the repository image | Health contracts, provider probes, sanitized configuration summary |
| `worker` | Separate process from the same image | Runtime heartbeat only; later Stories add engine work |
| `migrate` | One-shot Alembic command from the same image | Install the runtime heartbeat schema and enable pgvector |
| `postgres` | `pgvector/pgvector` pinned to a PostgreSQL 16 image digest | Local metadata/search provider and runtime heartbeat storage |
| Artifact storage | Compose named volume mounted at `/var/lib/kb2/artifacts` in application services | Read/write availability probe and persistent local bytes; S-002 owns Artifact semantics |

Generation is an optional external Provider port, not a Compose service.
`generation.default` selects DeepSeek `deepseek-v4-flash`, while
`generation.high_precision` selects `deepseek-v4-pro`. The shared base URL is
the exact trusted official endpoint `https://api.deepseek.com`. Local and
production configuration cannot override that host, scheme, or port. These
identifiers are constants in one non-secret capability configuration file and
are not duplicated through Compose and Python code.

`embedding.default` remains provider-neutral and `not_configured` in S-001.
DeepSeek does not provide an embeddings contract this design can depend on, and
a generation LLM must never be treated as an embedding provider. A later
Ingestion Story must select and evaluate an independent embedding Provider.

PostgreSQL serves both metadata and initial hybrid-search infrastructure so
S-001 does not introduce an additional search cluster before a query Story can
demonstrate that need. This is a local provider choice, not a permanent search
contract; later code reaches it through provider boundaries.

The application image and third-party images must be pinned to reproducible
versions. Do not use floating `latest` tags. Docker Compose service dependencies
use health/completion conditions so API and worker start only after PostgreSQL
is healthy and migrations finish. DeepSeek availability is not a service-start
dependency and cannot change core local readiness.

### Repository Layout

S-001 introduces only runtime-oriented modules:

```text
pyproject.toml
src/kb2_runtime/
  api.py
  config.py
  worker.py
  health/
    contracts.py
    service.py
    probes.py
  db/
    migrations/
deploy/local/
  compose.yaml
  compose.test.yaml
  capabilities.yaml
  Dockerfile
scripts/
  local_runtime.py
tests/
  contract/
  integration/
```

Engine packages and placeholder domain endpoints are not created. Shared
Artifact and Run contracts remain for S-002; Plugin registry and runners remain
for S-003.

### Developer Commands And Runtime CLI

Make targets are stable documentation aliases over
`python3 scripts/local_runtime.py`:

```text
make local-up
make local-health
make local-stop
make local-clean CONFIRM=kb2-local-data
make test-contract
make test-integration
```

The Python CLI centralizes Compose file selection, project naming, generated
state, timeout handling, and output sanitization. Make recipes must not repeat
or partially reimplement lifecycle logic. Defaults are:

- project: `kb2-lite-dev`;
- environment: `local`;
- state root: `.runtime/kb2-lite-dev/`;
- Compose file: `deploy/local/compose.yaml`.

Integration tests pass a unique DNS-safe project name, `test` environment,
temporary state root, and `compose.test.yaml` overlay to the same CLI. The CLI
executes Compose with an argument list rather than a shell string, validates
project names, resolves paths under the supplied state root, and rejects broad
or unsafe cleanup targets.

`local-up` performs these idempotent steps:

1. verify tool versions and required ports;
2. create the project state and secret directories with restrictive modes;
3. generate missing local credentials without printing them;
4. render only a non-secret configuration summary;
5. build and start Compose services with `--wait`;
6. invoke the same core health operation used by `local-health`.

`local-stop` resolves the exact Compose project and calls `down
--remove-orphans` without `--volumes`. It does not stop Docker globally, kill
ports, or address containers by loose name patterns. `local-clean` first
validates the confirmation token and target project/state path, then calls the
same scoped `down` with volume removal and deletes only that project's generated
state directory.

### Health And Capability Contract

Expose three endpoints:

```text
GET /health/live
GET /health/ready
GET /health/capabilities?require=<capability-id>&require=<capability-id>
```

`/health/live` performs no downstream call. It returns HTTP 200 with a minimal
schema containing contract version, `live`, and a timestamp.

`/health/ready` probes every default-required component concurrently with
per-probe deadlines. It returns the full sanitized report and HTTP 200 only
when all required components are ready; otherwise it returns the same schema
with HTTP 503.

`/health/capabilities` returns all declared component and capability entries.
The repeated `require` values add experiment-specific requirements to the
default set. Unknown capability IDs are rejected with HTTP 400 and a stable
code. It returns HTTP 503 when any effective required entry is unavailable.
The future Profile compiler can derive this list from an execution plan without
changing the endpoint. An empty `require` set never probes an external
generation provider, even when a key is configured; this applies equally to a
plain `/health/capabilities` request and `make local-health`. Only explicitly
required generation capability IDs authorize the corresponding external
readiness probe.

The versioned response shape is:

```json
{
  "contractVersion": "health/v1",
  "environment": "local",
  "status": "ready",
  "checkedAt": "2026-09-10T00:00:00Z",
  "components": [
    {
      "id": "metadata.postgres",
      "required": true,
      "status": "ready",
      "code": "OK",
      "latencyMs": 3
    }
  ],
  "capabilities": [
    {
      "id": "generation.default",
      "required": false,
      "status": "not_probed",
      "code": "NOT_PROBED",
      "provider": "deepseek",
      "model": "deepseek-v4-flash"
    }
  ]
}
```

Allowed entry statuses are `ready`, `unavailable`, `not_configured`, and
`not_probed`.
Allowed aggregate statuses are `ready` and `not_ready`. The committed
capability catalog declares stable IDs, provider IDs, default requirement,
probe type, public provider base URL, and model IDs. It contains no credentials
or private endpoints.

Initial required components are:

- `control.api` from the responding process;
- `metadata.postgres` from `SELECT 1`;
- `artifact.local` from a bounded create/read/delete probe under a reserved
  `.health` directory;
- `worker.default` from a database heartbeat with a defined freshness window.

No model capability is default-required. Without a non-empty DeepSeek key,
`generation.default` and `generation.high_precision` are `not_configured`.
When the key is present but neither generation capability is explicitly
required, both are `not_probed` with code `NOT_PROBED` and no authenticated
outbound request occurs. When the request set explicitly requires one or both,
one bounded authenticated request to DeepSeek's OpenAI-compatible `/models`
endpoint verifies provider reachability and exact presence of the requested
model IDs. An unrequested configured generation capability remains
`not_probed`, even if the same provider response happens to list its model. The
health path must not invoke generation and therefore must not incur
generation-token charges. Provider failure produces `unavailable`, and a
missing requested model produces `MODEL_NOT_AVAILABLE`. `embedding.default` is
always `not_configured` in this Story. Any of these states affects the aggregate
result only when the caller explicitly requires that capability.

`runner.container` is `not_configured` until S-003 supplies and registers that
runner; it is reported as optional rather than silently assumed.

The worker updates a single infrastructure-owned heartbeat row on a bounded
interval. Alembic owns that small table from the first migration. This is not a
Run or Stage record and must not grow into S-002 domain persistence.

Each probe catches errors at its boundary and maps them to allowlisted codes
such as `DEPENDENCY_UNAVAILABLE`, `HEARTBEAT_STALE`, `MODEL_NOT_AVAILABLE`, or
`PROBE_TIMEOUT`. The response and default log record may include only IDs,
status, code, bounded latency, and correlation ID. Exception messages, stack
traces, DSNs, HTTP bodies, filesystem contents, SQL, and model output never
enter health responses or generated test evidence. Debug exceptions remain
disabled for the local API and worker.

### Configuration And Secrets

`deploy/local/capabilities.yaml` and application defaults contain:

- environment identifier;
- provider IDs;
- DeepSeek base URL and model IDs;
- probe deadlines and heartbeat freshness;
- non-secret ports and paths inside containers.

The DeepSeek provider adapter owns a closed endpoint trust policy. When
`environment` is `local` or `production`, it accepts only the exact normalized
origin `https://api.deepseek.com` with standard TLS certificate validation. The
base URL is not an environment override in those modes. When `environment` is
exactly `test`, it accepts only `http://deepseek-fixture:8080`; all other
schemes, hosts, ports, user-info, path prefixes, query strings, or fragments are
rejected during configuration loading. The HTTP client does not follow
redirects and does not inherit proxy variables, preventing the mounted key from
being forwarded to an unreviewed destination. Supporting a proxy, another
vendor, or another DeepSeek endpoint later requires a separately reviewed
provider adapter and trust policy, not a generic URL redirect using this key.

Runtime connection material is read only from `*_FILE` paths. The local CLI
generates a PostgreSQL password using the Python standard library `secrets`
module and creates an empty DeepSeek-key file below the ignored project state
directory when one does not exist. Both files must be regular files with mode
`0600`; startup rejects a populated DeepSeek key file with broader permissions.
Compose mounts them as secrets and application configuration reads their
contents from the mounted files. The key value is never supplied as an
environment variable, command-line argument, Docker build argument, image
environment value, or health field. `.env` files and all of `.runtime/` are
ignored; a committed example may list file-path variable names but may not
contain credential-shaped placeholder values.

Provider clients receive typed, validated configuration. A safe configuration
summary returns only `environment`, provider IDs, capability IDs, and model
IDs. It must not serialize the full settings object or key-file contents.

### Isolated Integration Runtime

`compose.test.yaml` is a Compose overlay, not an alternate orchestration path.
It uses the same application image, API, worker, migration, PostgreSQL,
Artifact-volume, health schemas, capability catalog, and lifecycle CLI. The
base no-key test path starts no provider fixture. Tests that exercise configured
generation add a deterministic repository-owned OpenAI-compatible HTTP fixture
for `/models`. The overlay sets environment exactly to `test` and uses the only
allowed fixture URL, `http://deepseek-fixture:8080`; it does not provide a
generic base-URL override. This avoids calling DeepSeek or generating billable
content in CI while still testing provider-boundary behavior. Tests must not
claim model quality or DeepSeek conformance from the fixture.

The pytest integration fixture:

1. creates a temporary state directory and unique Compose project;
2. invokes CLI `up` and `health` as subprocesses;
3. writes non-sensitive sentinel data directly to the runtime database and
   Artifact volume through test helpers;
4. exercises stop/restart and verifies persistence;
5. checks no-key `not_configured`, configured-but-unrequested `not_probed`,
   zero outbound requests for plain health, then explicitly requires
   generation and checks present/missing model behavior against the fixture;
6. stops PostgreSQL to induce required failure, checks sanitized nonzero
   health, restarts it, and waits for recovery;
7. creates a second control project to verify scoped operations;
8. invokes CLI `clean` in `finally` and asserts target resources and generated
   secret files are absent.

Tests use bounded polling with monotonic deadlines, never fixed long sleeps.
Failure handling preserves only sanitized Compose status and health JSON; raw
container logs are available to the local developer on demand but are not
automatically copied into committed evidence.

## Relevant Impacts

### API And Compatibility

Health response objects are versioned as `health/v1`; fields are additive
within v1. Component and capability IDs are stable machine-readable values.
Later Engine Stories may add catalog entries and probes but must preserve
liveness semantics and may not make an optional capability required without an
explicit runtime configuration change.

No engine execution API, public document API, or UI endpoint is introduced.

### Data And Migration

The first Alembic migration enables pgvector and creates only the worker
heartbeat table. PostgreSQL and Artifact data live in project-scoped named
volumes. There is no model volume, production migration, or external data
import.

Normal restart is non-destructive. Removal is deliberately separate and cannot
target a workspace root, home directory, Docker's global state, or a project
other than the exact validated project name.

### Security And Observability

Compose publishes only the API port by default. PostgreSQL is reachable on an
internal project network but is not bound to the host. The API makes outbound
DeepSeek requests only when a key is configured and the request's explicit
`require` set contains a DeepSeek generation capability. Plain health calls
never make authenticated outbound requests.
Containers run as non-root where supported, the application filesystem is
read-only apart from explicit state mounts, and no Docker socket is mounted.
The API has no debug or documentation endpoint that exposes settings by
default.

Application logs are structured JSON containing timestamp, severity,
component, event code, and correlation ID. Health probes emit state-transition
events rather than logging every successful poll. Database passwords,
connection strings, request/provider bodies, document bytes, and raw exceptions
are excluded.

### Rollout

This is a new local-only baseline. Rollout consists of documenting prerequisites
and commands in the repository README, validating the no-key path on a clean
machine, and keeping runtime teardown scoped. It makes no production capacity,
security, Azure, DeepSeek availability, or model-quality claim.

## Alternatives And Risks

- **OpenSearch in the initial stack:** Rejected for S-001 because PostgreSQL
  plus pgvector provides a representative replaceable metadata/search provider
  with substantially lower local resource cost. A later Query Story may add an
  adapter and benchmark that justifies OpenSearch.
- **Pure host processes:** Rejected because their dependency installation and
  cleanup would not give the required isolated, reproducible lifecycle.
- **Docker Compose environment passwords or committed development passwords:**
  Rejected because they violate AC 5 and appear in inspection output. Generated
  file-mounted secrets keep the one-command workflow without embedding them.
- **Make recipes as orchestration:** Rejected because divergent dev/test logic
  would undermine AC 6. Make remains a thin alias over one typed CLI.
- **Running Ollama in the initial stack:** Superseded by the user-confirmed
  2026-09-11 DeepSeek decision. S-001 has no Ollama service, model initializer,
  model volume, or local model download.
- **Making external generation default-required:** Rejected because the core
  stack must start and report ready without a DeepSeek key or network access.
  Query Profiles opt into generation by explicitly requiring the capability.
- **Using DeepSeek generation as embedding:** Rejected because generation and
  embedding have different contracts and DeepSeek provides no embedding API
  this design can rely on. Embedding remains unconfigured until a later Story
  selects an independent Provider.
- **DeepSeek model or API drift:** `/models` proves only current reachability and
  advertised model presence, not stable behavior, quality, or context limits.
  Later execution/evaluation must snapshot the provider and model identifiers;
  stable error mapping prevents provider bodies from leaking.
- **External availability and rate limits:** Configured capability health can
  fail because of network, authentication, throttling, or provider outage.
  Bounded probes distinguish `not_configured` from `unavailable`, and none of
  these failures affect core readiness unless the capability is required.
- **Credential forwarding through configurable URLs, redirects, or proxies:**
  Rejected. Local/production accepts only `https://api.deepseek.com`, test
  accepts only `http://deepseek-fixture:8080`, redirects are not followed, and
  proxy environment variables are ignored. A new destination requires a new
  reviewed adapter and trust policy.
- **Test fixture drift from DeepSeek:** The fixture validates only the minimal
  OpenAI-compatible `/models` adapter contract. The fixture response is kept to
  that surface and makes no claim about generation quality or vendor
  conformance.
- **Development machine variability:** Docker memory, architecture, and ports
  can cause slow or failed startup. Preflight emits sanitized actionable codes,
  images are pinned, and timeouts are configurable. No model download is part
  of startup.
- **Probe side effects:** Artifact write probes use a reserved bounded file and
  delete it in `finally`; heartbeat has one bounded row. Neither may create
  user-visible domain data.

## Test Strategy

### Unit And Contract Tests

- Parse and validate configuration without reading secret values into safe
  summaries.
- Validate health/v1 serialization, stable ordering, status aggregation,
  `NOT_PROBED` representation, unknown required-capability rejection, and
  HTTP/CLI exit mappings.
- Exercise every probe success, unavailable, timeout, and unexpected-error
  mapping with canary secrets and provider payloads; assert none appear in
  responses or default logs.
- Validate project names, state-root containment, cleanup confirmation, Compose
  argument construction, and refusal of unsafe targets.
- Verify exact DeepSeek model matching from `/models`, no-key
  `not_configured`, configured-but-unrequested `not_probed`, zero external
  calls from plain health, no generation endpoint use, and no inference of
  model availability from HTTP reachability alone.
- Verify `embedding.default` remains provider-neutral and `not_configured` even
  when DeepSeek generation is ready.
- Reject every local/production DeepSeek URL except exact
  `https://api.deepseek.com`; accept the fixture URL only for exact `test`;
  verify redirects and inherited proxy variables cannot receive the key.

### Integration Tests

- Clean isolated no-key startup through the documented CLI and full core
  health, with no outbound DeepSeek request.
- Default readiness when generation is not configured, followed by nonzero
  selected-experiment health when generation is required.
- Configured-key plain `/health/capabilities` and `make local-health` return
  `not_probed`/`NOT_PROBED` and produce zero fixture requests.
- Configured fixture `/models` success for `deepseek-v4-flash` and
  `deepseek-v4-pro`, missing-model failure, provider failure, and recovery.
- Required PostgreSQL failure, nonzero health, sanitized output, recovery, and
  worker heartbeat recovery.
- Stop/restart persistence for a database sentinel and Artifact sentinel.
- Scoped stop and clean in the presence of another running project.
- Final resource inventory proving deterministic cleanup.

### Security Regression

- Inspect tracked files for forbidden secret material and verify `.runtime/`,
  `.env`, DeepSeek key files, private documents, and raw diagnostics are
  ignored.
- Inspect built application image configuration and history for canary secret
  absence.
- Inject a canary database password, DeepSeek API key, DSN, provider response,
  exception message, and Artifact text; assert none occurs in command
  arguments, container inspection, health JSON, CLI output, structured logs,
  or retained test evidence.
- Verify only the API host port is published and the Docker socket is absent.

The default fast test command runs unit and contract tests. Docker integration
tests are explicitly marked but are required for Story completion and CI on a
Docker-capable runner. `make harness-check` remains part of regression.

## Implementation Checklist

- [x] Add pinned Python dependencies, application image, Compose topology, and
  first Alembic migration.
- [x] Implement typed configuration loading, generated file-mounted local
  secrets, safe summaries, and ignore rules.
- [x] Implement API liveness, default readiness, capability readiness, probe
  timeouts, sanitization, and stable health/v1 contracts.
- [x] Implement worker heartbeat and Artifact/provider probes without adding
  later Story domain contracts.
- [x] Implement the single lifecycle CLI and thin Make targets for up, health,
  stop, explicit clean, and tests.
- [x] Add optional DeepSeek provider configuration for
  `deepseek-v4-flash`/`deepseek-v4-pro`, exact `/models` probing, and explicit
  provider-neutral `embedding.default` state.
- [ ] Gate all authenticated DeepSeek probes on explicit generation IDs in the
  `require` set and expose configured unrequested capabilities as
  `not_probed`/`NOT_PROBED`.
- [ ] Enforce the closed environment-to-endpoint trust policy, disable redirect
  following and proxy inheritance, and reject generic provider URL overrides.
- [x] Add mode-`0600` ignored DeepSeek key-file handling through a Compose
  secret; prove the core stack is ready without a key.
- [x] Add deterministic OpenAI-compatible `/models` fixture and isolated
  Compose test overlay without any real DeepSeek call.
- [x] Add unit, contract, integration, persistence, isolation, failure,
  recovery, cleanup, and security regression tests.
- [x] Document prerequisites, startup duration/resource expectations, health
  semantics, commands, optional capability checks, stop versus clean, and
  troubleshooting codes. README must state that plain health never contacts
  DeepSeek, show the explicit `--require generation.default` opt-in, document
  `not_configured` versus `not_probed`, identify the two trusted environment
  endpoints, and state that proxies or other vendors require a reviewed
  adapter rather than a URL override.
- [x] Run focused tests, Docker integration tests, secret scans, image checks,
  and `make harness-check`; retain sanitized evidence in the Story run log.

## Open Questions

None.

## Approval

Approved by Story Pipeline design delegation on 2026-09-10. The user explicitly
approved the external DeepSeek provider amendment on 2026-09-11. The
coordinator synchronized the upstream contracts before amended implementation.

## Change History

- **2026-09-10:** Approved initial S-001 technical design for implementation.
- **2026-09-11:** Replaced Ollama and local model initialization with optional
  external DeepSeek generation (`deepseek-v4-flash` default and
  `deepseek-v4-pro` high precision), left embedding unconfigured, and recorded
  the user-confirmed upstream contract change.
- **2026-09-11:** Restricted DeepSeek probing to explicitly required
  generation capabilities, added `not_probed`/`NOT_PROBED`, and closed endpoint
  trust to the official HTTPS origin plus the single exact test fixture URL.
