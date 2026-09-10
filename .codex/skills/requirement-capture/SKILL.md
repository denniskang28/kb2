---
name: requirement-capture
description: Incrementally capture multi-turn product analysis directly into a concise phased PRD. Use when starting a product, refining scope, confirming functional requirements, recording non-goals or open product questions, or reopening approved product scope without creating a separate requirements ledger.
---

# Requirement Capture

Maintain `docs/prd.md` as both the working product specification and the durable
requirement owner. Do not create a separate requirements ledger.

## Operations

- Initialize when no PRD exists.
- Checkpoint after a material topic closes or before context handoff.
- Finalize when the user says the functional scope is complete.
- Reopen only for an explicit product change; preserve stable IDs and history.

Read [prd-template.md](references/prd-template.md) before creating or
restructuring the PRD.

## Rules

1. Keep the PRD concise enough for frequent context loading.
2. Assign stable `REQ-###` IDs and a phase to independently traceable behavior.
3. Mark only explicit user confirmations or approved sources as `Confirmed`.
4. Keep AI suggestions in conversation unless the user accepts them; never
   generate requirements to fill a template.
5. Capture functional behavior, business rules, scope, and non-goals here.
   Route selected technical choices to `$core-design-capture`.
6. Preserve a concrete detail only when it changes observable behavior, Story
   acceptance, scope, authority, or a costly implementation choice.
7. Record blocking product questions; omit speculative completeness matrices.

Finalization sets the PRD to `Needs Approval`. Explicit user approval sets it to
`Approved`. Product approval does not approve core technical design, UI
prototype behavior, Features, or Stories.
