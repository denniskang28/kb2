# Story Design: S-006 - Representative Parser And OCR Plugins

## Status

Approved

## Story Contract Snapshot

- **Story:** `docs/stories/S-006-representative-parser-and-ocr-plugins.md`
- **Confirmed Version Or Date:** Confirmed 2026-09-11; pipeline delivery
  started 2026-09-11.
- **Material Decisions Requiring Approval:** None. The pipeline invocation
  authorizes the bounded adapter and fixture choices below. They preserve the
  registered-Plugin and Canonical-only engine boundaries.

## AC To Design Mapping

| AC | Implementation | Planned Verification |
|---|---|---|
| 1 | Bootstrap a native OOXML text Parser and a scanned bilingual OCR-exchange adapter. Each consumes a closed source Artifact, emits one adapter-specific provider Artifact, then uses a schema-specific normalizer registration to commit `canonical.document/v1`. | End-to-end executor tests run a sanitized DOCX and bilingual scanned-OCR fixture through their Parser/OCR and normalizer stages; assert typed intermediate and Canonical Artifacts. |
| 2 | Adapters materialize the existing strict `ProviderFixture` wire shape with PDF/word-processing locators, page geometry, ordered bilingual text, layout-derived headings/tables, language, and OCR quality signals. Schema-specific normalizers reuse `CanonicalNormalizer`; provider bytes never enter the Canonical output. | Golden Canonical assertions cover page/paragraph locators, reading order, Chinese and English text, metadata, and quality signals. |
| 3 | All source decoding, ZIP/XML parsing, OCR-exchange validation, model selection, result limits, and provider output validation occur inside the registered implementations. They raise stable existing Plugin errors so the executor writes exactly one failed attempt and no output Artifact. | Parameterized resilience matrix covers unknown/missing model, malformed OOXML/OCR input, timeout, pre- and mid-flight cancellation, injected adapter crash, and invalid provider result. |
| 4 | Add `parser.synthetic@1` in test support only, using the same source/provider schema pair and the unchanged normalizer descriptor/implementation. It is registered with descriptor, factory, and tests only. | An architecture test registers and invokes it without editing `PluginRegistry`, runner, executor, or canonical normalizer source. |
| 5 | Descriptors identify adapter implementation/digest and declared safe quality names; outputs carry only bounded counts, language/OCR/layout signals, and summaries. Existing executor lineage records adapter identity, config digest, timing, and parent Artifact IDs. | Trace assertions inspect manifests and stage evidence for adapter identity and bounded signals; canaries prove source/provider payload and credential-like text are absent from diagnostics. |

## Current Code Findings

S-003 supplies the process-local allowlist, frozen descriptors, bounded Plugin
output/result contracts, in-process/container runners, deadline and
cancellation handling, and atomic S-002 Artifact completion. Its executor
already makes the producing Plugin ID, configuration digest, source parents,
metrics, quality signals, terminal safe error, and timing traceable. It rejects
unknown Artifact schemas before an implementation starts.

S-005 supplies `ProviderFixture`, the strict bounded provider-to-Canonical
wire model, `CanonicalNormalizer`, deterministic Canonical serialization, and
the `normalizer.canonical@1` fixture registration. Its own approved design
explicitly reserves real revisioned Parser/OCR provider schemas and matching
normalizer registrations for this Story. The current schema catalog contains
only `opaque.bytes/v1`, `provider.parse-result-fixture/v1`, and
`canonical.document/v1`; no source-document or production provider result
schema exists. The runtime has no parser/OCR dependency or model bundled in
`pyproject.toml` or the local image.

## Proposed Approach

### Artifact And Adapter Boundary

Add these closed schema pairs to `trace.schemas`:

```text
source.native-ooxml/v1
source.scanned-ocr-exchange/v1
provider.native-ooxml-result/v1
provider.scanned-ocr-result/v1
```

The two `source.*` pairs are immutable input bytes, not filenames, URLs,
paths, SDK objects, or generic profile payloads. S-010 will own materializing
source documents and detection reports in a plan; this Story only proves the
adapter inputs directly through the existing executor. The strict descriptor
schema and its empty/closed configuration models remain the only invocation
surface.

`provider.native-ooxml-result/v1` and `provider.scanned-ocr-result/v1` are
both UTF-8 JSON serializations that validate as the existing S-005
`ProviderFixture` model. They are separately named because they are diagnostic
adapter outputs with distinct lineage and compatibility, even though their
normalized structural subset is currently common. No provider SDK object,
original archive/image bytes, model response body, command, credential, or
unbounded extension map crosses that Artifact boundary.

Register these descriptors in repository bootstrap:

```text
parser.native-ooxml@1
  source.native-ooxml/v1 -> provider.native-ooxml-result/v1
  runner=in_process, config={}

ocr.scanned-exchange@1
  source.scanned-ocr-exchange/v1 -> provider.scanned-ocr-result/v1
  runner=in_process, config={ model_id: "fixture-ocr-v1" }

normalizer.native-ooxml@1
  provider.native-ooxml-result/v1 -> canonical.document/v1

normalizer.scanned-ocr@1
  provider.scanned-ocr-result/v1 -> canonical.document/v1
```

The two normalizer registrations instantiate the unchanged
`CanonicalNormalizer`; only their already-explicit schema descriptor differs.
This honors the S-005 extension boundary and makes a new Parser adapter a
descriptor, implementation, and test addition rather than an orchestration or
normalizer contract change. The test-only `parser.synthetic@1` follows the
native pair and can use a deterministic provider-fixture factory.

### Native And Scanned Implementations

Place adapters in a focused `kb2_runtime.ingestion_adapters` module or package
owned by S-006, keeping `plugins.bootstrap` as registration-only wiring.

`NativeOoxmlParser` accepts only a bounded DOCX ZIP. It uses Python standard
library `zipfile` and `xml.etree.ElementTree`, rejects archive traversal,
unexpected/missing required parts, encrypted/oversized archives, XML parse
errors, and exceeding a fixed entry/text/page-equivalent limit before it builds
the typed provider fixture. The initial supported native shape is deliberately
minimal: document paragraphs and heading styles become ordered heading or
paragraph elements with `word_processing` locators. It records media type and
detected language only when deterministically derivable from the fixture. This
is a real native OOXML parsing path without a new package, host executable,
network call, or cloud provider.

`ScannedOcrExchangeAdapter` accepts a bounded, closed UTF-8 JSON OCR exchange
fixture representing a sanitized scanned bilingual page. It validates model
identity, page number, normalized bounding boxes, reading order, recognized
Chinese/English text, language tags, and bounded OCR confidence/layout
signals; then it converts that exchange shape to the S-005 `ProviderFixture`.
The only initially available model ID is `fixture-ocr-v1`. An absent or unknown
model is an explicit `PLUGIN_UNAVAILABLE` failure. This is intentionally an
adapter proof for the OCR boundary, not a claim that the local runtime bundles
a general raster recognition model. A later real OCR provider can register a
new descriptor/schema/model capability without changing executor or Canonical
contracts.

Both adapters produce provider Artifact bytes with deterministic JSON encoding
and a source digest derived from the input Artifact reference, rather than any
adapter-local timestamp or provider ID. The provider payload is capped below
the S-005 `MAX_PROVIDER_FIXTURE_BYTES` limit. They emit only safe bounded
metrics/signals: source byte count, element count, page count, layout detected,
languages observed, OCR model ID, and bounded confidence bucket. `quality_signal_names`
on each descriptor lists the emitted names.

### Failure, Cancellation, And Evidence

Do not change Registry, `PluginExecutor`, runner protocol, or Canonical model
contracts. Adapter validation failures use `PLUGIN_RESULT_INVALID`; unavailable
OCR model uses `PLUGIN_UNAVAILABLE`; unexpected implementation exceptions use
the runner's existing `PLUGIN_CRASHED`; deadline and cancellation retain the
existing runner codes. The executor remains responsible for starting/failing
one trace attempt and for preventing completion after every post-start error.

No models, external parser services, subprocess calls, filesystem paths,
environment values, credentials, network requests, or provider diagnostics are
accepted from Plugin configuration or retained in summaries/signals/errors.
Input Artifact content remains available only through the declared context and
the intermediate provider Artifact retains raw adapter diagnostics under the
existing Artifact store, not the stage record.

## Relevant Impacts

### Data And Compatibility

This extends only the closed in-code Artifact schema catalog and repository
bootstrap registrations. There is no database migration, API route, Compose
service, secret, external model download, or user-visible Profile change.
Existing `normalizer.canonical@1` and its fixture schema remain intact for
S-005 regression coverage. Later S-010 orchestration can select these
descriptors as declared Profile stages once it owns source/detection Artifact
creation.

### Security And Observability

Adapters are reviewed in-process code, receive only `PluginContext`, and use
no host command or runtime settings. ZIP processing must reject unsafe member
names and enforce aggregate and per-entry limits before extraction to avoid a
decompression resource attack. OCR exchange JSON must be decoded once with
strict Pydantic models and bounded strings/counts. Stage diagnostics remain
the existing safe generic messages; tests use provider-payload and
credential-like canaries to ensure they never leak through trace summaries,
signals, or errors.

## Alternatives And Risks

- Bundling Tesseract or a downloadable OCR model would produce a more general
  raster recognizer, but introduces host executables, model lifecycle, language
  data, and non-reproducible environment dependencies that are not established
  by this local runtime. The closed OCR exchange adapter proves the required
  Plugin/Artifact/normalization behavior while making model absence explicit.
- Parsing every OOXML format now would broaden format parity before S-007/S-010
  own structural routing. DOCX is the representative native path; presentation
  and spreadsheet locators remain supported by Canonical contracts for their
  later adapters.
- Reusing `provider.parse-result-fixture/v1` for production paths would be
  expedient but erases adapter provenance and violates S-005's intended
  revisioned production-output extension point. Distinct provider schemas keep
  diagnostic Artifacts typed and replaceable.

## Test Strategy

Add a self-contained sanitized fixture corpus under `tests/fixtures/ingestion/`:
a minimal DOCX containing a heading and paragraphs, plus a JSON scanned OCR
exchange containing one page with Chinese and English text, geometry, order,
and confidence. Fixture generation must be deterministic and contain no
proprietary source text.

Add `tests/contract/test_ingestion_adapters.py` for descriptor schemas,
catalog registrations, direct adapter conversion, output byte determinism,
typed provider validation, source digest/locator preservation, safe metrics,
and the synthetic adapter extension. Add
`tests/contract/test_ingestion_adapter_failures.py` for malformed/traversal or
oversized OOXML, malformed/bounds-invalid OCR exchange, missing model, injected
crash, timeout, and cancellation; every post-start scenario asserts one failed
trace and no committed output.

Add `tests/integration/test_parser_ocr_normalization.py` that executes both
complete Parser/OCR-to-normalizer chains with existing fake trace services (or
the established runtime fixture where appropriate). It asserts provider
Artifact schema, Canonical schema, exact parent lineage for each stage,
page/word-processing locators, ordered bilingual Canonical text, adapter ID,
quality evidence, and redaction. Retain all S-003/S-005 contract and full
regression suites; no Docker-specific test is required because the selected
adapters are deterministic in-process implementations.

## Implementation Checklist

- [ ] Add bounded native-OOXML and scanned-OCR-exchange input contracts plus
  deterministic provider-fixture conversion helpers in
  `kb2_runtime.ingestion_adapters`.
- [ ] Extend the Artifact schema catalog with the four source/provider pairs.
- [ ] Add and bootstrap the two Parser/OCR descriptors and two schema-specific
  normalizer descriptors without changing executor/runner/normalizer code.
- [ ] Add sanitized DOCX and bilingual OCR-exchange fixtures and direct
  contract/resilience coverage, including synthetic extension proof.
- [ ] Add Parser/OCR-to-Canonical integration coverage and run focused plus
  complete regression suites.

## Open Questions

None. The selected OCR exchange fixture is a deliberate bounded implementation
choice, not a new product claim about bundled general OCR capability.

## Approval

Pipeline invocation authorizes this just-in-time technical design. It records
implementation choices only and does not change the confirmed Story contract.

## Change History

- **2026-09-11:** Created for the S-006 Story Pipeline delivery run.
