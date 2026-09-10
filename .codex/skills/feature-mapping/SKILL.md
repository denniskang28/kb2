---
name: feature-mapping
description: Map an approved concise PRD, confirmed selective core design, and any adopted UI references into lean Feature routing manifests. Use after global analysis and normally after HTML prototype intake; create no Stories and require no exhaustive Feature design.
---

# Feature Mapping

Read `docs/current-state.md`, approved `docs/prd.md`, and only relevant DES/UI
anchors. The AI owns the initial decomposition; the user reviews capability
boundaries, not a second full design.

## Workflow

1. Group confirmed REQ items by user outcome, domain capability, or independently
   governed platform concern.
2. Assign stable `FEAT-###` IDs and preserve existing IDs.
3. Create a routing manifest that lists exact REQ, DES, and UI anchors,
   dependencies, shared risks, and the Story index.
4. Record a concise shared rule only when it affects multiple future Stories.
5. Set status to `Mapped`, `Needs Boundary Review`, or `Blocked`.
6. Mark `Optional Design Recommended` only when a material cross-Story journey,
   state model, authority rule, or data lifecycle remains unclear.

Read [feature-template.md](references/feature-template.md) before creating
`docs/features/FEAT-###-<slug>.md`. Maintain a concise `docs/feature-map.md`.

Do not invent Feature-local behavior, acceptance criteria, complete journeys,
UI matrices, APIs, schemas, technical designs, or code. A Feature does not need
a Feature Design before Story decomposition.
