# FEAT-005: Knowledge Engine Experiment Workbench

- **Status:** Mapped
- **Phase:** Lite Core
- **Optional Design:** Not Needed

## Outcome And Boundary

Give knowledge, document-AI, retrieval, and quality engineers one connected
local workbench for configuring Profiles, submitting representative documents,
inspecting typed pipeline stages and Artifacts, running evidence-grounded
queries, maintaining reviewed evaluation cases, and comparing experiments.

## Source Routing

- Requirements: `REQ-017`
- Core Design: `DES-001` through `DES-016`
- Feature Designs: `FD-001` through `FD-011`
- UI Brief: `docs/ui/prototype-brief.md`
- UI Reference: `docs/ui/reference.md` (`UI-001` through `UI-013`)

## Confirmed Shared Rules

- The workbench is an engineering tool, not a knowledge-management portal or
  marketing surface.
- It calls engine/control APIs and never implements Profile compilation,
  Plugin execution, metrics, or validation rules in the browser.
- Profile editing selects registered typed plugins and validated parameters; it
  cannot enter an arbitrary command or script path.
- Stage, Artifact, Evidence, metric, and failure views preserve the identifiers
  needed to navigate across ingestion, query, and evaluation diagnosis.
- Only the behaviors and visual scope explicitly adopted in
  `docs/ui/reference.md` are authoritative; its demo-only and not-adopted items
  remain non-requirements.

## Dependencies And Risks

- Depends on FEAT-001 through FEAT-004 contracts.
- Building screens before stage and Artifact contracts stabilize can create a
  second browser-only domain model; UI Stories must consume engine schemas.
- Dense diagnostics require deliberate progressive disclosure and responsive
  behavior to remain usable without turning every result into a dashboard card.

## Story Index

| Story | Outcome | Source Coverage | Status |
|---|---|---|---|
| S-022 | Workbench shell and runtime overview | UI-001, UI-002, UI-013 | Confirmed |
| S-023 | Profile and Plugin Studio | UI-006, UI-007, UI-013 | Confirmed |
| S-024 | Document, Ingestion Run, and Artifact inspection | UI-003, UI-004, UI-005, UI-013 | Confirmed |
| S-025 | Query Lab and Evidence inspection | UI-005, UI-008, UI-013 | Confirmed |
| S-026 | Evaluation Dataset and Evaluation Run | UI-009, UI-010, UI-013 | Confirmed |
| S-027 | Comparison and cross-Run diagnosis | UI-011, UI-012, UI-013 | Confirmed |
| S-028 | Persisted document list | UI-003, UI-005, UI-013 | Implemented |

All adopted UI-001 through UI-013 items are compiled into at least one Story.
Demo-only and not-adopted prototype items remain excluded from every Story.

## Open Boundary Questions

None. UI Reference v1 is confirmed. Story decomposition must preserve its
adoption boundary and consume engine schemas instead of prototype data models.

## Change History

- **2026-09-10:** Created and confirmed the dedicated workbench boundary.
- **2026-09-11:** Adopted and routed UI Reference v1 (`UI-001` through
  `UI-013`) after prototype intake.
- **2026-09-11:** Compiled S-022 through S-027 with Visual Acceptance Matrices;
  Story boundaries await user confirmation.
- **2026-09-11:** User confirmed S-022 through S-027 Story boundaries.
- **2026-09-14:** Compiled S-028 as the follow-up correction that restores the
  confirmed populated document-list behavior with persisted Run/Artifact data;
  its Story boundary awaits explicit confirmation.
- **2026-09-14:** User explicitly confirmed the S-028 Story boundary.
- **2026-09-14:** S-028 implemented the persisted API-backed document list,
  deterministic paging, Run/Artifact diagnosis actions, and responsive state
  coverage; independent verification and final review passed.
