---
name: core-design-capture
description: Capture only user-confirmed, high-value technical design discussed during global product analysis, including technology choices, architecture, data structures, APIs, core classes, algorithms, security, concurrency, and operational constraints. Use for selective design checkpoints without attempting a complete system design.
---

# Core Design Capture

Maintain `docs/core-design.md`. This document is selective by design: missing
topics remain for Story technical design.

## Operations

- Initialize when the first material technical topic is confirmed.
- Checkpoint after a decision or design topic closes.
- Finalize when the user has finished the desired global design discussion.
- Reopen for an accepted cross-Story technical change.

Read [core-design-template.md](references/core-design-template.md) before
creating or restructuring the document.

## Rules

1. Assign stable `DES-###` IDs.
2. Record type, status, strength, applicable REQ IDs or phase, decision, key
   details, rationale, and material alternatives.
3. Use strength `Binding Constraint`, `Preferred Direction`, or
   `Reference Example` so early class or algorithm ideas are not over-bound.
4. Mark only explicit user confirmation or an approved source as `Confirmed`.
5. Keep AI proposals conversational or `Proposed`; never promote them to make
   the design look complete.
6. Suggest additional discussion only for costly, cross-Story, irreversible,
   security-sensitive, data-contract, algorithmic, or architectural choices.
7. Do not create Feature designs, Stories, physical implementation plans, or
   code.

Relevant DES items are later compiled into Story contracts. Delivery agents do
not load this complete document by default after Story confirmation.
