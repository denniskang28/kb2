# Product Requirements

## Status

- **State:** Approved
- **Approved On:** 2026-09-10
- **Current Phase:** Lite Core
- **Source:** User confirmations on 2026-09-10

## Product Goal

Provide a local-first Knowledge Engine workbench that lets engineers define and
execute reusable document-ingestion and query Profiles, extend both engines
through stable plugins, and measure parsing, retrieval, citation, and answer
accuracy reproducibly across representative complex documents.

## Primary Users And Outcomes

| User | Intended outcome |
|---|---|
| Knowledge Engineer | Compose and tune processing/query Profiles without copying an end-to-end script. |
| Document-AI Engineer | Add a parser, OCR, structure, chunking, or enrichment implementation without changing the orchestration engine. |
| Retrieval Engineer | Compare retrieval, fusion, reranking, and context strategies against fixed evidence labels. |
| Quality Reviewer | Maintain reviewed ground truth and identify whether failures originate in ingestion, retrieval, or answer generation. |

## Functional Requirements

| ID | Requirement | Status | Source |
|---|---|---|---|
| REQ-001 | The complete core service stack runs locally with persisted artifacts and no required Azure service. Model integrations remain provider-neutral and may use explicitly configured external providers; their credentials and readiness do not gate the core runtime unless a selected Profile requires that capability. | Confirmed | User confirmation |
| REQ-002 | An Ingestion Profile declaratively composes reusable, allowlisted processing plugins; a Profile does not own or execute an arbitrary script. | Confirmed | User confirmation |
| REQ-003 | The engine validates plugin configuration and typed stage inputs/outputs before or during execution and rejects incompatible plans safely. | Confirmed | User confirmation |
| REQ-004 | A Profile may use explicit selection, deterministic document-class routing, and declared conditional branches while recording the resolved execution plan. | Confirmed | User confirmation |
| REQ-005 | A new document type or processing algorithm can be added through a plugin plus Profile configuration without modifying the orchestration engine. | Confirmed | User confirmation |
| REQ-006 | Parsing results normalize into one provider-neutral Canonical Document preserving content, hierarchy, reading order, tables, source locations, provenance, and quality signals. | Confirmed | User confirmation |
| REQ-007 | Every ingestion run exposes stage state, inputs, outputs, metrics, quality signals, timing, and actionable failures for diagnosis and evaluation. | Confirmed | User confirmation |
| REQ-008 | The initial engine supports representative native, scanned, layout-rich, table-heavy, presentation, spreadsheet, and long-hierarchical document strategies through reusable components rather than one script per business document type. | Confirmed | User confirmation |
| REQ-009 | A Query Profile declaratively composes query analysis, rewrite, retrieval, fusion, reranking, context assembly, generation, verification, repair, and abstention stages as applicable. | Confirmed | User confirmation |
| REQ-010 | Query stages can use different retrieval strategies for text, hierarchy, tables, and other document structures while returning a common citation-ready Evidence contract. | Confirmed | User confirmation |
| REQ-011 | Generated answers use retrieved evidence, expose stable source citations, and abstain or request clarification when the configured evidence requirement is not met. | Confirmed | User confirmation |
| REQ-012 | Reviewers can define a Golden Dataset containing questions, expected and forbidden facts, relevant evidence, required citations, answerability, and document/question classification labels. | Confirmed | User confirmation |
| REQ-013 | Evaluation separately measures document understanding, retrieval quality, answer correctness, groundedness, citation quality, and abstention behavior rather than hiding them in one score. | Confirmed | User confirmation |
| REQ-014 | A comparison fixes the dataset, input artifacts, resolved execution plans, plugin/model/prompt identities, and parameters, then reports quality, latency, and resource results independently. | Confirmed | User confirmation |
| REQ-015 | Accuracy targets and hard failures can be defined per document class and question class; deterministic checks are preferred where available and LLM judges require calibration against human labels. | Confirmed | User confirmation |
| REQ-016 | Parser, OCR, embedding, search, reranking, and model integrations remain provider-neutral so local implementations can later be replaced by Azure adapters without changing engine contracts. | Confirmed | User confirmation |
| REQ-017 | A thin local console supports document submission, explicit or automatic Profile selection, run inspection, querying, evaluation execution, and comparison inspection. | Confirmed | User confirmation |

## Lite Non-goals

- Enterprise SSO, roles, groups, tenants, knowledge-base ACLs, or administration.
- Publication, approval, rollback, user-facing document/Profile versioning, or
  lifecycle governance.
- File-size quotas, capacity allocation, billing, retention, DLP, legal hold,
  or enterprise source synchronization.
- Production HA/DR, multi-region deployment, or managed-service conformance.
- Azure AI Search, Blob Storage, Service Bus, Key Vault, Entra ID, Azure OpenAI,
  or Document Intelligence in the initial local runtime.
- A general-purpose workflow product or arbitrary-code visual DAG editor.

## Success Criteria

1. At least three materially different complex-document classes execute through
   shared plugins and different resolved Ingestion Profiles.
2. Adding one new parser or document strategy requires no orchestration-engine
   modification.
3. At least two Query Profiles can be compared over the same indexed artifacts.
4. A failed evaluation case can be traced to ingestion, retrieval, context, or
   answer-generation evidence.
5. The demonstration and evaluation loop is orchestrated locally from
   documented commands and persists its non-sensitive artifacts; configured
   model calls may use an explicitly selected external provider.

## Open Product Questions

None currently blocking Feature decomposition. Exact initial document fixtures,
metric thresholds, and provider/model choices belong to Story design and
benchmark calibration unless they change the scope above.

## Change History

- **2026-09-10:** Initialized and approved the Lite Core scope from the user's
  confirmed ingestion, query, and evaluation focus.
- **2026-09-11:** User selected an external DeepSeek generation provider instead
  of a locally hosted Ollama model; clarified the local-first provider boundary.
