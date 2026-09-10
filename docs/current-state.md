# Current State

- **As Of:** 2026-09-10
- **Harness State:** Lite Harness Initialized
- **Product Requirements:** Approved - 2026-09-10 (17 confirmed REQs)
- **Core Design:** Approved - 2026-09-10 (16 confirmed DES records)
- **Feature Map:** Confirmed - 2026-09-10 (5 Features)
- **Feature Designs:** 3 Approved (FD-001 through FD-011)
- **UI Prototype Brief:** Ready - 2026-09-10
- **Claude Design Prompt:** Ready - 2026-09-10
- **UI Prototype / Reference:** Not Yet Generated / Not Adopted
- **Stories:** 3 Confirmed (S-001 through S-003)
- **Active Story:** None
- **Application/Test Baseline:** None

## Current Boundary

Knowledge Engine Lite is scoped to a local experiment runtime, configurable
document ingestion, configurable evidence-grounded query execution, and
reproducible layered evaluation. Profiles compile declarative configuration to
resolved execution plans. Reusable allowlisted Plugins implement typed stages.
All parsing paths converge on a provider-neutral Canonical Document; query paths
converge on citation-ready Evidence and validated final states. Evaluation
separates ingestion, retrieval, answer, citation, abstention, latency, and local
resource results.

Enterprise identity, authorization, administration, publication, approval,
rollback, quota, file-size policy, retention, source connectors, managed Azure
services, and HA/DR are explicitly outside the Lite boundary. Internal digests,
revisions, lineage, and snapshots required to reproduce experiments do not
reintroduce user-facing version-management scope.

The project-level Codex agents, skills, Story Pipeline configuration, and lean
workflow were copied from `../kb` and adapted to this engine-first boundary. No
application code, technical implementation design, test suite, benchmark
corpus, or adopted UI reference has been established. FEAT-005 owns the thin
experiment workbench, and its Claude Design generation prompt is ready.

## Recommended Next Action

Run `story-pipeline-agent S-001`; after its delivery, S-002 and S-003 can
establish the shared Artifact/Trace and Plugin/Runner contracts. Run
`$feature-to-stories FEAT-002` after these boundaries are confirmed so the
ingestion Stories can reference stable prerequisites without pre-planning the
complete system. FEAT-003 and FEAT-004 can be decomposed after their required
Artifact and Canonical contracts are represented in confirmed Stories.
Generate the external FEAT-005 prototype from `docs/ui/claude-design-prompt.md`,
then run `$ui-reference-intake <prototype-path>` before decomposing UI Stories.

## Change History

- **2026-09-10:** Initialized the Lite Harness, approved product/core design,
  and confirmed four Feature boundaries.
- **2026-09-10:** Approved three shared Feature designs covering FD-001 through
  FD-011.
- **2026-09-10:** Added FEAT-005 and prepared the external UI prototype brief
  and Claude Design prompt.
- **2026-09-10:** Compiled FEAT-001 into S-001 through S-003; all three await
  explicit Story boundary confirmation.
- **2026-09-10:** User confirmed S-001 through S-003; S-001 is next for
  delivery.
