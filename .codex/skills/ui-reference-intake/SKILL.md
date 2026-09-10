---
name: ui-reference-intake
description: Analyze an external HTML prototype, screenshots, design export, or UI demo and create one concise governed UI reference with stable UI IDs. Use after prototype creation and before Feature mapping or Story planning so only adopted screens, regions, states, and interactions become downstream context.
---

# UI Reference Intake

Inspect the supplied artifact and the minimum relevant PRD/Core Design anchors.
Do not copy prototype implementation into application code.

## Workflow

1. Ensure the source has a durable path. Ask before copying an external package
   into `docs/ui/prototypes/<version>/`.
2. Inventory only meaningful screens, regions, components, flows, and states.
3. Separate `Adopted Behavior`, `Visual Reference`, `Demo Data`, `Prototype
   Implementation`, `Not Adopted`, and `Open Question`.
4. Assign stable `UI-###` IDs to adopted or intentionally referenced items.
5. Map each UI item to exact REQ/DES anchors and its route, file, selector,
   state, or screenshot region.
6. For each `Visual Reference` item that may drive downstream acceptance,
   record the observable comparison context available from the source: viewport
   or responsive context, UI state, stable regions, and any confirmed allowed
   deviations. Put material missing context in `Open UI Questions`; do not
   invent it.
7. Ask the user only when prototype behavior changes or extends approved product
   behavior. Route accepted product changes through `$update-prd`.
8. After confirmation, write or update the single active
   `docs/ui/reference.md` using [ui-reference-template.md](references/ui-reference-template.md).

Do not create Features, Stories, Feature designs, or code. A prototype is not
authoritative until its relevant behavior is explicitly adopted.
