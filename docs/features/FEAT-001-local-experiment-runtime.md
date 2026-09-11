# FEAT-001: Local Experiment Runtime

- **Status:** Mapped
- **Phase:** Lite Core
- **Optional Design:** Not Needed

## Outcome And Boundary

Run ingestion, query, and evaluation work locally through one consistent
execution substrate, persist non-sensitive artifacts, and inspect every run
without introducing enterprise operational infrastructure.

## Source Routing

- Requirements: `REQ-001`, `REQ-007`
- Core Design: `DES-001` through `DES-004`, `DES-008`, `DES-016`
- UI Reference: None

## Confirmed Shared Rules

- The Plugin Registry is allowlisted and declares typed configuration and
  Artifact schemas.
- Profiles compile into immutable execution-plan snapshots before work starts.
- Stage traces contain references and bounded diagnostics, not large raw
  payloads or credentials.

## Dependencies And Risks

- No Feature dependency.
- External model credentials/network requirements and complex-parser resource
  requirements must remain explicit so a healthy control API cannot falsely
  imply every provider or plugin is runnable.
- Artifact storage and trace identity must be stable before higher Features
  build incompatible ad hoc persistence.

## Story Index

| Story | Outcome | Status |
|---|---|---|
| S-001 | Start and inspect the complete local runtime and capability readiness | Implemented |
| S-002 | Persist immutable Artifacts and common Run/Stage trace evidence | Implemented |
| S-003 | Register and invoke typed Plugins through equivalent local runners | Implemented |

## Open Boundary Questions

None.

## Change History

- **2026-09-10:** Created and confirmed the Feature boundary.
- **2026-09-10:** Compiled S-001 through S-003; awaiting Story boundary
  confirmation.
- **2026-09-10:** User confirmed S-001 through S-003.
- **2026-09-11:** User selected external DeepSeek for generation and removed
  Ollama from the initial runtime boundary.
- **2026-09-11:** S-001 implementation, verification, and final review passed.
- **2026-09-11:** S-002 and S-003 delivered into local main.
