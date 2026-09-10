---
name: test-and-regression
description: Add, update, and run automated tests for one Story or approved batch using the Story acceptance contract, technical design, implementation diff, and current regression surface. Use after implementation and during repair loops without loading full upstream planning documents by default.
---

# Test And Regression

Read the Story, approved Story design, exact UI artifact regions named by them,
implementation diff, relevant code, and existing tests. Retrieve other upstream
sources only when a concrete contract conflict or stale Story requires
provenance inspection.

## Workflow

1. Build an AC-to-test inventory.
2. Add applicable unit, integration, contract, API, UI, workflow, permission,
   security, migration, observability, performance, accessibility, visual, and
   regression evidence in proportion to risk.
3. For every `Visual Acceptance Matrix` row, produce the required evidence. When
   screenshot comparison is applicable:
   - capture the reference and implementation under equivalent, reproducible
     conditions;
   - record the browser/runtime, viewport, pixel density, theme, locale, data
     fixture, font and asset readiness, and animation handling that materially
     affect the result;
   - limit masks to genuinely dynamic regions and document each mask;
   - retain the diff or overlay needed to diagnose visible discrepancies.
4. Use only acceptance methods, allowed deviations, and tolerances supported by
   the Story or approved design. Treat material missing comparison conditions as
   an unclear Story or stale design instead of inventing or relaxing them.
5. Change a visual baseline only when confirmed UI or Story evidence authorizes
   the change. Never update a baseline merely to make an implementation pass.
6. Run focused tests first and broader gates second.
7. Preserve valid regression tests.
8. Classify failures as implementation, test, environment, unclear Story,
   stale design, architecture conflict, or missing dependency.
9. Return actionable feedback to development or the correct contract owner.

Use [test-report-template.md](references/test-report-template.md). Never weaken
valid acceptance or regression tests to pass.
