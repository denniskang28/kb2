# Claude Design Prompt

- **Target:** Claude Design interactive canvas and Artifact output
- **Derived From:** `docs/ui/prototype-brief.md`
- **Product Source:** REQ-017, with REQ-001 through REQ-016 as displayed
  engine behavior
- **Design Sources:** DES-001 through DES-016 and FD-001 through FD-011
- **Feature:** FEAT-005
- **Usage:** Paste the complete prompt below into Claude Design. Generated UI is
  exploratory until it passes UI reference intake and explicit adoption.

## Prompt

```text
Create a high-fidelity, responsive, interactive engineering application in
Claude Design as one coherent design Artifact. Start building the application
immediately. Do not begin with an explanation, design plan, requirements recap,
landing page, hero, or marketing content.

PRODUCT

The product name is "Knowledge Engine Lite". It is a local-first engineering
workbench for configuring, running, diagnosing, evaluating, and comparing
complex-document ingestion and evidence-grounded query pipelines.

Use Simplified Chinese for UI copy. Keep established engineering nouns such as
Profile, Plugin, Artifact, Run, Evidence, Recall@K, MRR, NDCG, RRF, OCR, and
Embedding in English where that improves precision. This is an internal tool
for knowledge engineers, document-AI engineers, retrieval engineers, and
quality reviewers. It is not a general employee knowledge portal.

If Claude Design generates implementation code, create a React interactive
Artifact with semantic HTML and local in-memory state. Use Lucide icons where
available. Make every required route and critical state navigable in the same
Artifact. Do not call a backend, external API, model, authentication service, or
remote asset. Do not include credentials or private endpoints.

CORE DOMAIN MODEL

Preserve these distinctions throughout the interface:

- A Profile is declarative YAML/JSON configuration compiled into a validated,
  resolved execution plan.
- A Plugin is reusable allowlisted implementation code selected by a stable ID
  such as parser.layout-local@1 or chunker.parent-child@2.
- A Profile never owns an independent script and cannot contain an arbitrary
  shell command, filesystem script path, or executable code.
- Stages exchange typed immutable Artifact references.
- All parser paths normalize to CanonicalDocument/v1.
- Query retrieval paths normalize to EvidenceSet/v1 with citation-ready source
  locators.
- A Run pins the resolved Profile plan, Plugin identities, inputs, parameters,
  models/prompts where applicable, and output Artifacts for reproducibility.
- Internal revision IDs and digests are diagnostic metadata, not a user-facing
  publication/version-management workflow.
- Accuracy is measured separately for ingestion, retrieval, answer quality,
  groundedness, citation, abstention, latency, and local resource usage.

PRODUCT EXCLUSIONS

Do not implement, advertise, or create disabled "coming soon" navigation for:

- SSO, users, roles, groups, permissions, tenants, or access administration.
- Knowledge-base governance, approval, publication, rollback, archive, or
  document lifecycle management.
- File-size quotas, pricing, billing, retention, DLP, legal hold, or malware
  administration.
- Azure AI Search, Azure Blob, Azure OpenAI, Document Intelligence, Service Bus,
  Key Vault, Entra ID, managed-service setup, HA, or disaster recovery.
- SharePoint, Microsoft 365, website, or other enterprise source connectors.
- Chatbot configuration, public Web chat, saved conversation history, or
  end-user feedback.
- A general-purpose workflow product or unrestricted code/shell editor.

APPLICATION SHELL

Build the actual workbench as the first screen. Use a quiet, compact,
work-focused application shell optimized for repeated technical diagnosis:

- Persistent desktop left navigation about 216-224 px wide.
- Compact top context bar with breadcrumbs, local-runtime indicator, current
  workspace/dataset context, and a small global run-status area.
- Main content should be unframed full-width work surfaces with constrained
  inner widths only where reading requires it.
- Use dense readable tables, split panes, tabs, drawers, inspectors, toolbars,
  status chips, and dialogs. Do not wrap page sections in floating cards and do
  not put cards inside cards.
- Cards may be used only for individual repeated result items or genuinely
  framed tools, with border radius no greater than 8 px.
- Prefer icon buttons for familiar actions such as run, stop, retry, inspect,
  compare, download, add, remove, and reorder; provide tooltips for unfamiliar
  icons.
- Use stable dimensions for stage nodes, toolbars, status cells, tables, metric
  plots, and inspector panes so state changes do not shift the layout.

Primary navigation:

1. 工作概览
2. 文档实验
3. Profile Studio
4. Query Lab
5. 评测集
6. 实验对比
7. 运行记录
8. Plugin Registry

VISUAL DIRECTION

Use a light neutral work surface with white, near-white, charcoal, and medium
gray as the foundation. Use restrained teal/green for healthy/selected states,
blue for informational selection and links, amber for warnings or fallback,
and red for failure. Do not make the UI a one-hue blue/slate, purple, beige,
brown, or orange theme. Do not use gradients, decorative orbs, bokeh, glass
effects, oversized headings, negative letter spacing, or viewport-scaled type.

Typography should be compact and highly legible. Reserve page-scale headings
for page identity; panel and inspector headings must remain small and tight.
Use real-looking synthetic document thumbnails, source-page previews, table
previews, stage diagrams, and metric charts as functional visual assets rather
than decorative illustrations.

REQUIRED CONNECTED SCREENS

1. 工作概览

- Show recent ingestion, query, and evaluation Runs in one dense activity
  table, with type, Profile, input, status, duration, and start time.
- Show local dependencies and Plugin runner availability in a compact status
  band, not a large dashboard-card grid.
- Show a concise queue of failed Runs requiring inspection and recent Profile
  comparisons.
- Primary commands are 上传文档, 新建 Profile, 打开 Query Lab, and 运行评测.
- Include populated, first-use empty, dependency-unavailable, and recoverable
  refresh-error states.

2. 文档实验

- Provide a compact document table with document name, detected format,
  processing class, selected Ingestion Profile, last Run, state, and actions.
- Add an upload/file-picker interaction using synthetic local files. After
  selection show preflight detection results such as MIME, page/sheet/slide
  count, language, scan ratio, table density, and layout complexity.
- Let the user explicitly choose a Profile or select 自动匹配. For automatic
  selection, show the matched rules and why one Profile was selected.
- Include representative documents: native PDF, scanned Chinese/English PDF,
  table-heavy spreadsheet/report, presentation, and long hierarchical manual.
- Starting ingestion must navigate to the new Ingestion Run detail.

3. Ingestion Run Detail

- Use a stable horizontal or vertical typed stage flow, not a decorative node
  cloud. Example stages: Detect, Parse, OCR, Normalize, Structure, Chunk,
  Enrich, Embed, Index, Validate.
- Demonstrate SUCCEEDED, RUNNING, FAILED, SKIPPED_BY_CONDITION,
  FALLBACK_SELECTED, CANCELLED, and RETRYING states. Do not imply that every
  Profile runs every stage.
- Selecting a stage opens a persistent inspector with Plugin ID and runner,
  validated configuration, typed input/output Artifact references, duration,
  metrics, quality signals, attempt, and structured error.
- Show the resolved Profile plan and digest separately from the authored
  Profile. Show routing decisions, matched features, conditions, and explicit
  fallback acceptance results.
- Provide working run, stop, retry failed stage, rerun as new experiment, and
  open Artifact actions. Retry preserves the same plan; changing a Plugin or
  Profile creates a new Run.

4. Artifact Inspector

- Open as a route or large split-pane drawer from any Run.
- Support tabs for 原始预览, Canonical, 结构树, 表格, Chunks, Metadata, and
  Lineage as applicable to the Artifact type.
- Canonical view synchronizes a structured element tree with a source preview;
  selecting an element highlights its PDF page/region, slide/object,
  sheet/range, or heading/paragraph locator.
- Table view shows rows, columns, cells, headers, merged spans, captions, and
  exact source location.
- Chunk view shows token count, parent/child relationship, canonical element
  IDs, overlap, metadata, and citation locator. Do not expose raw vector arrays.
- Lineage shows parent Artifacts and producing Run/stage/Plugin/digest without
  presenting a publication-version timeline.

5. Profile Studio

- Provide tabs for Ingestion Profiles and Query Profiles, plus searchable
  Profile lists with working status, component summary, last validation, and
  digest.
- The Profile editor has synchronized 表单 and YAML modes. YAML is declarative
  configuration only, with syntax/schema errors and no command execution.
- Ingestion Profile form composes extraction, structure, chunking, enrichment,
  embedding, and indexing components.
- Query Profile form composes Analyze, Rewrite, Route, Retrieve, Fuse, Rerank,
  Context, Generate, Verify, Repair, and Abstain as applicable.
- Add/reorder/remove stages through accessible controls. A stage chooses only a
  compatible Plugin from the Registry; its parameter form is generated from a
  synthetic schema. Show typed input/output ports, condition builder, timeout,
  and explicit fallback candidates.
- Include validation states for unknown Plugin, incompatible Artifact schema,
  unbound input, invalid condition, missing required parameter, and valid
  compiled plan.
- Commands: 验证, 编译预览, 保存工作配置, 试运行, and 复制为候选. Do not add
  approval, publish, rollback, or production activation.

6. Plugin Registry

- Create a dense searchable/filterable catalog grouped by Detect, Parser, OCR,
  Normalizer, Structure, Chunker, Enricher, Embedding, Index, Retriever,
  Fusion, Reranker, Context, Generator, Verifier, Metric, and Judge.
- Rows show stable Plugin ID, kind, runner type, accepted input schemas, output
  schemas, capabilities, local availability, implementation digest, and last
  contract-test result.
- Plugin detail shows configuration schema, typed contracts, resource hints,
  timeout, example safe configuration, and recent Runs.
- Registry is inspectable configuration, not a place to paste scripts, install
  remote packages, or enter arbitrary container commands.

7. Query Lab

- Use a focused three-part work surface: question/Profile controls, pipeline
  execution evidence, and final answer/citation result.
- Let the user select indexed document Artifacts and a Query Profile, enter a
  synthetic question, and run or cancel the query.
- Show the resolved Query plan and stage timing.
- Retrieval inspection shows separate keyword, vector, hierarchy, or table
  candidate lists; then fusion, rerank, context-selection decisions, and safe
  scores in a dense comparison table.
- Evidence panel shows selected excerpts, citation keys, source document,
  locator, contributing retrievers, and why an item entered or left context.
- Answer panel supports ANSWERED, CLARIFICATION_REQUIRED, ABSTAINED, FAILED,
  VERIFY_FAILED, and REPAIRING. Citations open the synchronized source preview.
- Demonstrate a high-precision factual query, a table-cell query, a hierarchical
  multi-evidence query, an ambiguous query, and an unanswerable query.

8. 评测集

- Use tabs for 文档标注 and 查询用例.
- Document annotations support source text/span, element type/order,
  table/cell/span, source locator, and expected evidence-preservation labels.
- Query cases include question, expected facts, forbidden facts, relevant
  Evidence, required citations, answerability, optional deterministic answer,
  and reviewer state.
- Slice labels include document format, native/OCR, structure class, language,
  question class, difficulty, and criticality.
- Provide dense list/detail editing, validation, review/mark-reviewed action,
  filters, and first-use/invalid/incomplete states. Generated synthetic cases
  must remain unreviewed until a deliberate review action.

9. Evaluation Run Detail

- Show a pinned run manifest containing dataset snapshot, Ingestion and Query
  plan digests, Artifacts, Plugins, models/prompts, metric definitions, Judge
  identity, slice taxonomy, and local runtime summary.
- Present separate metric bands for Ingestion, Retrieval, Answer, Citation,
  Decision/Abstention, and Operations. Do not create one overall quality score.
- Include CER/WER, element F1, reading-order accuracy, table/cell accuracy,
  locator accuracy, Recall@K, MRR, NDCG@K, evidence hit rate, context
  precision/recall, fact coverage, correctness, completeness, groundedness,
  citation precision/recall, and abstention precision/recall where applicable.
- Clearly show NOT_APPLICABLE and INSUFFICIENT_LABELS rather than converting
  them to zero or hiding them.
- Filter by slice and metric. Clicking a failed bar/cell drills to case rows;
  selecting a case shows the exact ingestion, retrieval, Evidence, generation,
  verification, annotation, and metric evidence.
- Show RUNNING, COMPLETED_WITH_FAILURES, PASSED_GATES, FAILED_GATES,
  INVALID_DATASET, and JUDGE_UNCALIBRATED states.

10. 实验对比

- Let the user select one Baseline Run and one or more Candidate Runs only when
  their pinned inputs and dataset are comparable. Explain incompatibility with
  concise field-level reasons.
- Show a matrix grouped by metric layer and slice with baseline, candidate,
  absolute delta, relative delta, sample count, and gate result.
- Use compact diverging bars or dot plots paired with the exact table. Do not
  use decorative gauges or one opaque ranking.
- Keep quality, latency, and local resource results in separate tabs or bands.
- Highlight regression, improvement, insufficient sample, and hard failure
  using icon, text, and color.
- Support one-component-axis attribution and label multi-axis comparisons as
  non-causal. Drill from every regression to exact failed cases and Artifacts.

11. 运行记录

- Provide one filterable table for ingestion, query, evaluation, comparison,
  and plugin contract-test Runs.
- Filters: run type, state, Profile, Plugin, document class, time, and trace ID.
- Preserve filters and selected row when navigating to details and back.
- Include active, completed, failed, cancelled, and orphaned/incomplete local
  Run states with safe recovery actions.

REQUIRED PROTOTYPE INTERACTIONS

- All navigation items, breadcrumbs, tabs, dialogs, drawers, table rows,
  filters, split panes, and primary commands must work with local state.
- Uploading a synthetic document must populate detection results; automatic
  Profile selection must reveal matched rules; starting a Run must navigate to
  its progress/detail screen.
- Profile Studio must support adding/reordering a stage, selecting a compatible
  Plugin, editing parameters, switching form/YAML views, showing a validation
  failure, and compiling a valid plan.
- Ingestion stage selection must change the inspector and Artifact links.
- Query execution must show waiting/progress and a selected final scenario;
  citation clicks must open the exact source preview.
- Evaluation metric/slice selection must update the case table; a failed case
  must navigate to its complete evidence chain.
- Comparison selectors and metric-layer tabs must update the report.
- Include a compact prototype-only scenario control outside the simulated
  product shell if needed to review hard-to-reach failure states. Mark it
  clearly as a prototype control, not product UI.

ACCESSIBILITY AND RESPONSIVE EXPECTATIONS

- Target WCAG 2.2 AA contrast, semantic landmarks, correct heading order,
  visible keyboard focus, complete keyboard navigation, labeled controls,
  accessible tables, and announced asynchronous status changes.
- Never rely on color alone; pair status color with icon and text.
- Design primarily for 1440 px and 1280 px desktop, then verify at 768 px and
  390 px. At narrow widths use a navigation drawer and convert master/detail
  split panes into sequential full-width routes or sheets.
- Dense tables should become readable record summaries; do not force clipped
  text, microscopic columns, horizontal control overlap, or hidden commands.
- All button labels, Plugin IDs, Artifact IDs, metric names, YAML text, long
  Chinese document names, and error messages must fit their containers.

SYNTHETIC DEMO DATA

Use only obviously fictional, non-sensitive data. Include examples such as:

- 采购框架合同示例.pdf: native, long hierarchical, several tables.
- 设备维护手册扫描示例.pdf: mixed Chinese/English OCR and layout warning.
- 季度经营数据示例.xlsx: table-heavy, multiple sheets and merged cells.
- 产品架构说明示例.pptx: slide/object locators and diagrams.
- 差旅制度示例.docx: heading hierarchy and exact policy questions.

Use neutral Plugin IDs such as parser.layout-local@1, ocr.zh-en-local@1,
normalizer.canonical@1, chunker.parent-child@2, retriever.keyword@1,
retriever.vector-local@1, fusion.rrf@1, reranker.local-cross-encoder@1, and
verifier.citation@1. Do not use real employee names, emails, IDs, customer data,
credentials, or production-looking endpoints. Mark all quality values as
synthetic prototype data.

DELIVERABLE

Return one polished, connected, runnable React design Artifact containing all
required routes and states. The result must be inspectable and exportable,
remain fully functional without network access, and make the actual engineering
workflows usable rather than explaining them with feature-description text.
Continue until the document-to-ingestion-run-to-artifact, query-to-evidence-to-
answer, and dataset-to-evaluation-to-comparison journeys are all demonstrable.
```
