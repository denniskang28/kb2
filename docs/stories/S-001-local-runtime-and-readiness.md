# S-001: Local Runtime And Readiness

- **Parent Feature:** FEAT-001
- **Status:** Confirmed
- **Phase:** Lite Core
- **Priority:** P0
- **Dependencies:** None

## Outcome

Let an engineer start, inspect, restart, and stop the complete Lite service
stack and representative local providers without requiring an Azure service,
while distinguishing basic process health from the availability of capabilities
needed by an experiment.

## Context Manifest

| Source | Exact Anchor | Snapshot State |
|---|---|---|
| REQ | `docs/prd.md#REQ-001` | Approved 2026-09-10 |
| DES | `docs/core-design.md#DES-001` | Confirmed 2026-09-10 |
| DES | `docs/core-design.md#DES-016` | Confirmed 2026-09-10 |
| Feature | `docs/features/FEAT-001-local-experiment-runtime.md` | Mapped 2026-09-10 |

## Inherited Requirements And Constraints

- The complete service stack and representative models run locally, preserve
  their non-sensitive data across a normal restart, and require no Azure
  service. `[REQ-001]`
- The runtime supports a thin control surface and three separately owned
  engines without absorbing their domain logic. `[DES-001]`
- Local Artifact, metadata/search, model, and processing-provider boundaries
  remain replaceable by future provider adapters; local health is not Azure
  conformance evidence. `[DES-016]`
- A healthy control process must not imply that every optional or resource-heavy
  Plugin/provider capability is currently runnable. `[FEAT-001]`

## Scope

- Reproducible local service startup, readiness reporting, restart, and scoped
  shutdown.
- Local configuration and persistent non-sensitive runtime storage.
- Aggregate and component-level capability health for the control surface,
  stores, model/search providers, and Plugin runner dependencies selected by
  the delivered local runtime.
- Documented developer commands and sanitized diagnostics.

## Non-goals

- Implementing Ingestion, Query, Evaluation, Profile, Artifact, or Plugin domain
  behavior owned by later Stories.
- Azure connectivity, managed-service compatibility, HA/DR, autoscaling, or
  production capacity claims.
- Enterprise identity, authorization, quotas, publication, or governance.
- Selecting a technology solely to preserve the architecture of `../kb`.

## Acceptance Criteria

1. One documented local command prepares and starts every required Lite service
   and representative local provider from a clean development checkout without
   requiring an Azure endpoint or credential.
2. A documented health command reports each required component and capability
   separately, uses a nonzero result for a required unavailable dependency, and
   does not expose credentials, private content, or raw provider errors.
3. Basic liveness remains distinguishable from readiness to execute a selected
   experiment, including when an optional heavy model or Plugin runner is not
   loaded.
4. A normal stop and restart affects only this project and preserves configured
   non-sensitive runtime data; deliberate data removal is a separate explicit
   operation.
5. Local configuration identifies the environment and provider selections
   without embedding secrets in committed files, images, commands, health
   output, or generated evidence.
6. The same documented startup and health path is executable in an isolated
   integration-test environment with disposable storage and deterministic
   cleanup.

## Verification Intent

| AC | Evidence Needed | Test Level |
|---|---|---|
| 1, 4 | Clean startup, scoped stop, restart, and persistence scenarios | Integration |
| 2, 3 | Required/optional dependency and capability-health matrix | Integration and contract |
| 5 | Secret/config/image/output scan | Security regression |
| 6 | Ephemeral runtime lifecycle with success and induced failure | Integration |

## Open Questions

None. Exact local database, search, model runtime, container topology, and
developer command names are material Story-design choices constrained by the
acceptance criteria above.

## Relationships And Blocks

- Enables S-002 and S-003.
- Later FEAT-002 through FEAT-004 Stories add executable capabilities to this
  runtime without changing its local-only product boundary.

## Change History

- **2026-09-10:** Compiled from confirmed FEAT-001 sources.
- **2026-09-10:** Story boundary confirmed by the user.
