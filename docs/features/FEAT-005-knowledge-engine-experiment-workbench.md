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

## Confirmed Shared Rules

- The workbench is an engineering tool, not a knowledge-management portal or
  marketing surface.
- It calls engine/control APIs and never implements Profile compilation,
  Plugin execution, metrics, or validation rules in the browser.
- Profile editing selects registered typed plugins and validated parameters; it
  cannot enter an arbitrary command or script path.
- Stage, Artifact, Evidence, metric, and failure views preserve the identifiers
  needed to navigate across ingestion, query, and evaluation diagnosis.
- Synthetic prototype data and reviewer controls do not become product
  requirements without UI reference intake and explicit adoption.

## Dependencies And Risks

- Depends on FEAT-001 through FEAT-004 contracts.
- Building screens before stage and Artifact contracts stabilize can create a
  second browser-only domain model; UI Stories must consume engine schemas.
- Dense diagnostics require deliberate progressive disclosure and responsive
  behavior to remain usable without turning every result into a dashboard card.

## Story Index

Not yet decomposed. Suggested boundaries: application shell and navigation;
Profile/Plugin Studio; Document and Ingestion Lab; Query Lab and Evidence
inspection; Golden Dataset and Evaluation views; Profile comparison and
cross-run diagnosis.

## Open Boundary Questions

None. The external prototype is an exploration input and must pass UI reference
intake before any generated behavior becomes authoritative.

## Change History

- **2026-09-10:** Created and confirmed the dedicated workbench boundary.
