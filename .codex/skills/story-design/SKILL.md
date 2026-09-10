---
name: story-design
description: Create a just-in-time technical design for one confirmed self-contained Story or a tightly coupled batch. Use before coding to align Story acceptance with current code, selecting only relevant UI artifacts and retrieving upstream REQ, DES, UI, or FD sources when staleness or conflict requires it.
---

# Story Technical Design

Require one or more confirmed Story IDs.

## Default Context

Read `AGENTS.md`, `docs/current-state.md`, each Story, exact relevant UI artifact
locations named by the Story, direct dependencies, and current code/tests. Do
not load complete PRD, Core Design, Feature, or Feature Design documents by
default. Resolve an upstream anchor only when the Story snapshot is stale,
ambiguous, contradictory, or insufficient.

## Workflow

1. Verify the Story is self-contained and has no material open question.
2. Inspect current code and executable contracts.
3. Map each AC to implementation and planned verification.
4. Decide modules, interfaces, data changes, algorithms, migrations, security,
   observability, rollout, and tests only as applicable.
5. Write `docs/designs/stories/S-###-<slug>.md` using
   [story-design-template.md](references/story-design-template.md).
6. When invoked independently, ask only questions that materially affect
   product behavior, public API, durable data, architecture, security,
   migration, or verification validity, and require explicit approval for
   those choices.
7. When invoked by `story-pipeline`, record those technical choices in the
   design and return it to the pipeline for immediate development. The pipeline
   invocation authorizes the design; do not request separate user approval.

The Story owns product behavior; the technical design may not silently change
it. Return product gaps to Story planning, cross-Story gaps to optional Feature
design, and global gaps to PRD/Core Design workflows.
