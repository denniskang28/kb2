---
name: partial-ui-reference-intake
description: Analyze one specified screen region, component, state, or interaction from an external UI reference and update only its exact UI anchor and affected Story context. Use for narrow UI changes when full prototype intake would be unnecessary.
---

# Partial UI Reference Intake

Require a source and bounded target. Inspect only enough surrounding state to
understand that target.

1. Identify the existing or candidate UI ID and exact artifact location.
2. Separate visual guidance, adopted behavior, demo data, and implementation.
3. Map the target to exact REQ, DES, Feature, and Story IDs when they exist.
4. Ask for confirmation only if product behavior or Story acceptance changes.
5. Update `docs/ui/reference.md` after confirmation; update an unstarted Story
   context only when its contract is explicitly reconfirmed.
6. Route global product changes to `$update-prd` and material cross-Story gaps
   to optional `$feature-design`.

Do not broaden scope, perform full intake, or implement code.
