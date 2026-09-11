# Feature Map

## Status And Sources

- **State:** Mapped
- **Mapped On:** 2026-09-10
- **Boundary Confirmed On:** 2026-09-10
- **Requirements:** `docs/prd.md` - Approved, REQ-001 through REQ-017
- **Core Design:** `docs/core-design.md` - Approved, DES-001 through DES-016
- **UI Reference:** `docs/ui/reference.md` - Confirmed for FEAT-005 (`UI-001`
  through `UI-013`); none required for FEAT-001 through FEAT-004
- **Coverage:** All 17 requirements have one primary Feature owner.

## Feature Routes

| ID | Feature | Phase | Primary Requirements | Dependencies | Optional Design |
|---|---|---|---|---|---|
| FEAT-001 | Local Experiment Runtime | Lite Core | REQ-001, REQ-007 | None | Not Needed |
| FEAT-002 | Configurable Ingestion Engine | Lite Core | REQ-002 through REQ-006, REQ-008 | FEAT-001 | Approved |
| FEAT-003 | Configurable Query Engine | Lite Core | REQ-009 through REQ-011 | FEAT-001, FEAT-002 | Approved |
| FEAT-004 | Reproducible Quality Evaluation | Lite Core | REQ-012 through REQ-016 | FEAT-001, FEAT-002, FEAT-003 | Approved |
| FEAT-005 | Knowledge Engine Experiment Workbench | Lite Core | REQ-017 | FEAT-001 through FEAT-004 | Not Needed |

REQ-007 is owned by FEAT-001 because the common Run Trace and Artifact
substrate serves ingestion, query, and evaluation. REQ-016 is owned
by FEAT-004 because provider substitution is accepted only when the common
evaluation contracts can compare it; provider ports remain shared Core Design.

## Confirmed Shared Rules

- Profiles are configuration compiled to a resolved execution plan; Plugins
  contain reusable implementation code.
- Engines exchange typed immutable Artifacts and use the same run/trace model.
- Canonical Document separates provider-specific parsing from downstream
  chunking, indexing, retrieval, and evaluation.
- Accuracy is measured by layer and classification slice; no single score may
  hide a retrieval, grounding, citation, or abstention failure.
- Local-first implementations and future Azure adapters share contracts but
  require separate conformance evidence.

## Suggested Planning Order

1. FEAT-001 establishes local execution, Artifact, Plugin Registry, and Trace
   foundations.
2. FEAT-002 establishes Profile compilation, Canonical Document, representative
   parsers, structure processing, chunking, and indexing.
3. FEAT-003 establishes composable retrieval through grounded final response.
4. FEAT-004 establishes reviewed datasets, layer metrics, hard gates, and
   reproducible Profile comparison.
5. FEAT-005 exposes these capabilities through a thin, connected experiment
   workbench after the engine contracts are represented in Stories.

Evaluation contract Stories should begin as soon as FEAT-002 Artifact schemas
exist, even though full end-to-end evaluation depends on FEAT-003.

## Change History

- **2026-09-10:** Mapped and confirmed four Lite Core Feature boundaries from
  the approved PRD and Core Design.
- **2026-09-10:** Approved shared designs for FEAT-002 through FEAT-004.
- **2026-09-10:** Added and confirmed FEAT-005 as the dedicated experiment
  workbench boundary; moved REQ-017 from FEAT-001.
- **2026-09-11:** Routed the confirmed Claude Design UI Reference v1 to
  FEAT-005; engine Features remain UI-independent.
