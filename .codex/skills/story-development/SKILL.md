---
name: story-development
description: Implement one confirmed Story or approved batch from its self-contained Story contract and approved technical design. Use after the design gate; default to Story-local context and current code rather than loading global planning documents.
---

# Story Development

Require Story IDs and approved Story design paths.

## Context

Read `AGENTS.md`, the Story, Story technical design, exact UI artifact regions
named by them, relevant code, and owned tests. Do not load full PRD, Core
Design, Feature, or Feature Design documents unless a concrete stale-source or
contract conflict requires provenance inspection.

## Workflow

1. Confirm the Story and design remain current.
2. Implement the smallest coherent change satisfying the ACs.
3. Add or update tests naturally owned by the change.
4. Map ACs to changed code and tests.
5. Record design deviations and route any product-contract conflict upstream.

Do not invent behavior, weaken tests, or expand scope.

## Handoff

```md
# Development Handoff
## Story And Design
## Files Changed
## AC-to-Code Mapping
## Tests Added Or Updated
## Deviations And Conflicts
## Build Status
```
