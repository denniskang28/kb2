---
name: ui-prototype-brief
description: Generate a focused prompt for an external AI UI design tool from an approved or stable PRD and confirmed core design. Use when preparing an HTML prototype request that must preserve product scope, roles, flows, states, and technical constraints without letting the design tool invent business behavior.
---

# UI Prototype Brief

Read the concise PRD and only relevant confirmed Core Design records. Accept an
optional target design tool; otherwise write a tool-neutral HTML prototype
prompt.

Read [prototype-brief-template.md](references/prototype-brief-template.md) before
writing `docs/ui/prototype-brief.md`.

## Workflow

1. Select the REQ and DES anchors that affect product experience.
2. Describe required users, screens, flows, information, states, responsive
   behavior, accessibility, and visual direction.
3. Separate fixed product behavior from areas where the design tool may explore.
4. Require inspectable HTML/CSS/JS output and clear navigation between states.
5. Require demo data to be synthetic and visibly non-authoritative.
6. Record source IDs so later intake can distinguish invention from input.

Do not add product requirements, public contracts, permissions, or data
semantics merely to make the prototype comprehensive.
