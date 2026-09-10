# Lean Harness Workflow

## Minimal Entry Points

```text
requirements-agent
$feature-mapping
$feature-to-stories FEAT-###
story-pipeline-agent S-###
```

Use `feature-design-agent FEAT-###` only when shared cross-Story behavior needs
an additional design round.

Use `$ui-reference-intake <prototype-path>` only if a future experiment-console
prototype becomes an accepted delivery source. UI design is not a gate for the
engine-first Features.

## Lifecycle

```text
multi-turn product analysis
  -> concise approved PRD (REQ)
  -> selective confirmed Core Design (DES)
  -> optional adopted UI reference anchors (UI)
  -> lean Feature routing manifests
  -> optional shared Feature design (FD)
  -> self-contained Story contracts
  -> just-in-time Story technical design
  -> development -> test -> review
```

## Progressive Context

Global analysis can be broad. Story decomposition compiles only the relevant
REQ, DES, optional UI, shared Feature, and optional FD evidence into each Story. After
Story confirmation, the delivery pipeline uses the Story and Story technical
design as its default contracts and does not repeatedly load complete global
planning documents.

For this repository, a Profile is declarative data and a Plugin is allowlisted
implementation code. A Story must not introduce arbitrary executable Profile
content or a script-per-document architecture. Reproducible run snapshots are
part of the engine contract even though user-facing version management is out
of scope.

If an upstream source changes, recompile only Stories that reference the changed
ID. Mark an affected unstarted Story `Needs Confirmation` and its existing
technical design `Stale`. Preserve implemented Story history.
