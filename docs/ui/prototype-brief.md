# UI Prototype Brief

## Target Tool And Output

- **Target:** Claude Design interactive canvas and Artifact output.
- **Output:** One inspectable, runnable React prototype with local state and no
  backend or network dependency.
- **UI language:** Simplified Chinese, retaining precise English engineering
  nouns where useful.
- **Scope:** FEAT-005 Knowledge Engine Experiment Workbench.
- **Status:** Ready for prototype generation. Generated behavior is not adopted
  until UI reference intake and explicit confirmation.
- **Canonical ready-to-paste prompt:** `docs/ui/claude-design-prompt.md`.

## Product And Phase

Design the Lite Core engineering workbench for a local-first Knowledge Engine.
It is used to configure and run complex-document ingestion, inspect Canonical
and downstream Artifacts, execute evidence-grounded queries, author reviewed
evaluation data, diagnose quality failures, and compare Profiles.

It is not an enterprise knowledge-management portal. UI value comes from
making pipeline state, intermediate evidence, configuration, and measurement
inspectable rather than from administrative breadth.

## Source Requirements And Design Constraints

- Product UI requirement: `REQ-017`.
- Displayed local/runtime and engine behavior: `REQ-001` through `REQ-016`.
- Shared architecture and contracts: `DES-001` through `DES-016`.
- Ingestion behavior: `FD-001` through `FD-004`.
- Query behavior: `FD-005` through `FD-007`.
- Evaluation behavior: `FD-008` through `FD-011`.

The UI must preserve these boundaries:

- Profiles are declarative configuration compiled to resolved plans.
- Plugins are reusable allowlisted implementations, not Profile-owned scripts.
- Stages exchange typed immutable Artifact references.
- Parsing converges on `CanonicalDocument/v1`.
- Retrieval converges on citation-ready `EvidenceSet/v1`.
- Evaluation layers and classification slices remain separate.
- The browser invokes engine/control APIs; it does not duplicate engine logic.

## Users And Required Workflows

### Knowledge / Document-AI Engineer

1. Submit a representative document and inspect detected characteristics.
2. Explicitly select a Profile or inspect automatic selection reasons.
3. Run ingestion and diagnose every stage, Plugin, Artifact, quality signal,
   condition, fallback, retry, and failure.
4. Inspect synchronized source, Canonical structure, tables, chunks, and
   lineage.
5. Compose and validate Profiles from registered typed Plugins.

### Retrieval Engineer

1. Select indexed Artifacts and a Query Profile.
2. Run text, hierarchy, table, high-precision fact, ambiguous, and unanswerable
   scenarios.
3. Inspect retriever candidates, fusion, rerank, context selection, Evidence,
   citations, generation, verification, repair, and final state.
4. Compare candidate Query Profiles over fixed inputs.

### Quality Reviewer

1. Maintain reviewed document annotations and query cases.
2. Run layered evaluation against pinned plans and Artifacts.
3. Filter results by document/question slice and metric layer.
4. Drill from a failed aggregate metric to its case, stage, Artifact, Evidence,
   output, verification, and label.
5. Inspect deterministic and calibrated-Judge results separately.

## Required Screens And Navigation

Use a compact persistent shell with these connected destinations:

1. **工作概览:** recent Runs, local dependency/runner health, failed work, and
   recent comparisons.
2. **文档实验:** document table, synthetic upload, detection, Profile selection,
   and ingestion start.
3. **Ingestion Run Detail:** typed stage flow, selected-stage inspector,
   resolved plan, routing/fallback reasons, metrics, errors, and Artifact links.
4. **Artifact Inspector:** synchronized source/Canonical tree, table, chunk,
   metadata, locator, and lineage views.
5. **Profile Studio:** Ingestion/Query Profile list, form/YAML editing, typed
   stages, compatible Plugin selection, conditions, fallback, validation, and
   compiled-plan preview.
6. **Plugin Registry:** stable ID, kind, runner, schemas, capabilities,
   availability, digest, contract tests, configuration schema, and recent Runs.
7. **Query Lab:** question/Profile controls, per-stage candidates and timing,
   selected Evidence, final state, citations, source preview, and cancellation.
8. **评测集:** document annotations, query cases, expected/forbidden facts,
   relevant Evidence, citations, answerability, review, and slice labels.
9. **Evaluation Run Detail:** pinned manifest, layer metrics, slices, gates,
   Judge calibration states, cases, and complete failure diagnosis.
10. **实验对比:** comparable baseline/candidates, per-layer/per-slice deltas,
    sample counts, gates, latency/resources, and case drill-down.
11. **运行记录:** one filterable registry for ingestion, query, evaluation,
    comparison, and Plugin contract-test Runs.

## Required States And Feedback

- Common: initial empty, loading/running, populated, recoverable error,
  dependency unavailable, terminal failure, cancelled, and stale refresh.
- Profile: valid, unknown Plugin, incompatible Artifact schema, unbound input,
  invalid condition, missing parameter, and compiled plan.
- Ingestion: succeeded, running, failed, skipped by condition, explicit fallback
  selected, retrying, and cancelled.
- Query: answered, clarification required, abstained, failed, verification
  failed, repairing, and cancelled.
- Evaluation: running, passed gates, failed gates, completed with case failures,
  invalid dataset, insufficient labels, not applicable, and uncalibrated Judge.
- Comparison: improvement, regression, hard failure, insufficient sample,
  incomparable inputs, one-axis experiment, and named multi-axis experiment.

## Fixed Product Rules

- Profiles cannot enter or execute arbitrary scripts, commands, credentials, or
  unrestricted environment values.
- Raw vectors and unbounded provider payloads do not appear in UI contracts.
- Retry preserves the resolved plan; modified configuration starts a new Run.
- `ANSWERED` requires supporting Evidence and citations; insufficient evidence
  results in clarification or abstention.
- No aggregate score hides layer or hard-slice failure.
- LLM Judge results show calibration state and cannot substitute for available
  deterministic checks.
- Internal digests and revisions support reproduction but do not introduce
  publication history, approval, rollback, or production activation.
- Do not add identity, governance, quotas, lifecycle, Azure configuration,
  connectors, Chatbots, public chat, HA/DR, or marketing/coming-soon surfaces.

## Areas Open To Visual Exploration

- Linear stage-flow orientation and selected-stage inspector placement.
- Source/Canonical synchronization and Artifact detail presentation.
- Profile stage composition using list, structured flow, split pane, or drawer.
- Candidate/fusion/rerank comparison layout.
- Metric/slice charts paired with exact data tables.
- Failure navigation using drawers, split panes, breadcrumbs, or dedicated
  detail routes.

Exploration must not invent new engine semantics, states, permissions,
workflows, or provider behavior.

## Accessibility And Responsive Expectations

- Target WCAG 2.2 AA, semantic landmarks, labelled controls, visible focus,
  keyboard navigation, accessible tables, and announced asynchronous updates.
- Use icon, text, and color together for status.
- Primary design widths: 1440 px and 1280 px; verify at 768 px and 390 px.
- At narrow widths, convert split panes to sequential routes/sheets and dense
  tables to readable record summaries without overlap or clipped controls.
- Use stable dimensions for stages, toolbars, status cells, plots, and
  inspectors; do not scale font size with viewport width.

## Synthetic Demo Data Rules

- Use only fictional documents, Plugins, profiles, endpoints, and metrics.
- Include native, OCR, table-heavy, presentation, and long-hierarchical
  examples with Chinese and mixed-language content.
- Mark metric values as synthetic prototype data.
- Do not include real people, companies, customer data, credentials, or private
  endpoints.

## HTML Deliverable Requirements

- One connected high-fidelity React Artifact with semantic DOM and local state.
- No backend, external request, model invocation, authentication, or remote
  asset dependency.
- All routes, primary commands, tabs, filters, drawers, dialogs, and required
  state transitions work.
- Use Lucide icons where available; unfamiliar icon controls have tooltips.
- Use functional document previews, tables, stage diagrams, and metric plots as
  visual assets; avoid decorative illustrations.
- Avoid landing/hero composition, gradients, decorative orbs, glass effects,
  nested cards, oversized headings, and a one-hue palette.

## Ready-to-use Prompt

```text
Create a high-fidelity responsive React prototype named "Knowledge Engine
Lite". Start with the actual application, not an explanation, landing page, or
marketing hero. Use Simplified Chinese UI copy while retaining precise English
engineering terms such as Profile, Plugin, Artifact, Run, Evidence, Recall@K,
MRR, NDCG, RRF, OCR, and Embedding.

This is a local-first engineering workbench for reusable complex-document
ingestion, evidence-grounded query pipelines, and layered quality evaluation.
A Profile is declarative YAML/JSON compiled to a resolved plan. A Plugin is
allowlisted reusable implementation selected by stable ID; Profiles never own
or execute arbitrary scripts. Stages exchange typed immutable Artifacts,
parsers normalize to CanonicalDocument/v1, and retrieval produces citation-
ready EvidenceSet/v1. Evaluation keeps ingestion, retrieval, answer, citation,
abstention, latency, and resource metrics separate.

Build one connected prototype with these destinations and detail routes:

1. 工作概览: recent Runs, local dependency/runner health, failures, comparisons.
2. 文档实验: synthetic upload, document detection, explicit/automatic Profile
   selection with matched-rule explanation, and ingestion start.
3. Ingestion Run: typed Detect/Parse/OCR/Normalize/Structure/Chunk/Enrich/Embed/
   Index/Validate flow, selected-stage inspector, resolved plan, inputs/outputs,
   metrics, quality signals, conditions, fallback, retry, stop, and errors.
4. Artifact Inspector: synchronized source/Canonical structure, table, chunk,
   metadata, source locator, and lineage views; never show raw vectors.
5. Profile Studio: Ingestion and Query Profiles, synchronized form/YAML modes,
   compatible registered Plugin selection, typed ports, conditions, explicit
   fallback, generated parameter forms, validation, and compiled-plan preview.
6. Plugin Registry: stable IDs, kinds, runners, schemas, capabilities, local
   availability, digests, contract tests, and read-only detail. No script paste
   or arbitrary container command.
7. Query Lab: Profile/question controls, separate retriever candidates, fusion,
   rerank, context decisions, Evidence, stage timing, answer verification,
   citations/source preview, repair, clarification, abstention, and failure.
8. 评测集: reviewed document annotations and query cases with expected and
   forbidden facts, relevant Evidence, required citations, answerability, and
   document/question slice labels.
9. Evaluation Run: pinned manifest; separate ingestion, retrieval, answer,
   citation, decision, and operation metrics; gates; slice filters; Judge
   calibration; drill-down from a failed metric to exact stage evidence.
10. 实验对比: comparable baseline/candidates, per-layer and per-slice deltas,
    sample counts, hard gates, separate latency/resources, and case drill-down.
11. 运行记录: filterable ingestion/query/evaluation/comparison/contract-test
    Runs with preserved list/detail context.

Make navigation, tabs, filters, dialogs, drawers, upload simulation, stage
selection, Profile editing/validation, run progress, query scenarios, citation
opening, metric filtering, failure drill-down, and comparison selection work
with local state. Demonstrate success, running, skipped condition, fallback,
retry, cancelled, failure, answered, clarification, abstained, verification
failed, invalid dataset, insufficient labels, uncalibrated Judge, regression,
improvement, hard failure, and incomparable comparison states.

Use a compact 216-224 px desktop navigation, dense tables, split panes,
inspectors, tabs, restrained charts, and stable stage/status dimensions. Use a
light neutral base, charcoal text, teal/green healthy states, blue information,
amber warnings, and red failures. Avoid gradients, purple dominance, beige or
dark-slate monotone themes, decorative orbs, glass effects, oversized headings,
nested cards, and explanatory marketing copy. Use Lucide icons and functional
synthetic document/source/table previews as visual assets.

Target WCAG 2.2 AA and keyboard operation. Verify 1440, 1280, 768, and 390 px.
At narrow widths use a navigation drawer, sequential detail routes/sheets, and
readable record summaries without overlap or clipped controls.

Use only fictional local documents, neutral Plugin IDs, and visibly synthetic
metrics. Do not add SSO, roles, tenants, governance, approval, publication,
rollback, quotas, billing, retention, DLP, Azure services, source connectors,
Chatbots, public chat, saved conversation history, HA/DR, or coming-soon UI.
Return one polished runnable React Artifact with semantic DOM, no backend,
external API, model call, authentication, credentials, or remote dependency.
```

For Claude Design, `docs/ui/claude-design-prompt.md` is the expanded canonical
variant with exact per-screen interactions and synthetic examples.
