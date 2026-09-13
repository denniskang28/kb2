from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Annotated
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from kb2_runtime.canonical.contracts import ProviderFixture
from kb2_runtime.canonical.normalizer import MAX_PROVIDER_FIXTURE_BYTES
from kb2_runtime.plugins.contracts import PluginContext, PluginInvocationResult, PluginOutput
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

MAX_SOURCE_BYTES = 512 * 1024
MAX_PDF_SOURCE_BYTES = 16 * 1024 * 1024
MAX_PDF_PAGES = 1_000
MAX_PDF_PAGE_TEXT = 16_384
MAX_PDF_ELEMENT_TOKENS = 480
MAX_ZIP_ENTRIES = 64
MAX_XML_BYTES = 256 * 1024
MAX_OCR_PAGES = 32
MAX_OCR_ITEMS = 512
_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_CONTENT_TYPES_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
_RELATIONSHIPS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_OFFICE_DOCUMENT_RELATIONSHIP = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
_HEADING = re.compile(r"^Heading([1-9])$")


class OcrExchangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model_id: Annotated[str, Field(min_length=1, max_length=64)] = "fixture-ocr-v1"


class OcrItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    order: int = Field(ge=0, le=MAX_OCR_ITEMS)
    text: str = Field(min_length=1, max_length=16_384)
    language: Annotated[str, Field(pattern=r"^[A-Za-z0-9+.-]{1,64}$")]
    bbox: tuple[float, float, float, float]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    layout: Annotated[str, Field(pattern=r"^(?:paragraph|heading)$")]

    @model_validator(mode="after")
    def normalized_bbox(self) -> "OcrItem":
        x0, y0, x1, y1 = self.bbox
        if min(self.bbox) < 0 or max(self.bbox) > 1 or x1 < x0 or y1 < y0:
            raise ValueError("OCR bounding box must be normalized")
        return self


class OcrPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    page_number: int = Field(gt=0, le=MAX_OCR_PAGES)
    items: tuple[OcrItem, ...] = Field(min_length=1, max_length=MAX_OCR_ITEMS)

    @model_validator(mode="after")
    def ordered_items(self) -> "OcrPage":
        if [item.order for item in self.items] != list(range(len(self.items))):
            raise ValueError("OCR items must have contiguous reading order")
        return self


class OcrExchange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model_id: Annotated[str, Field(min_length=1, max_length=64)]
    pages: tuple[OcrPage, ...] = Field(min_length=1, max_length=MAX_OCR_PAGES)

    @model_validator(mode="after")
    def ordered_pages(self) -> "OcrExchange":
        if [page.page_number for page in self.pages] != list(range(1, len(self.pages) + 1)):
            raise ValueError("OCR pages must be contiguous")
        return self


def _provider_bytes(payload: dict[str, object]) -> bytes:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_PROVIDER_FIXTURE_BYTES:
        raise PluginError(PluginErrorCode.RESULT_INVALID)
    try:
        ProviderFixture.model_validate_json(encoded)
    except ValidationError as exc:
        raise PluginError(PluginErrorCode.RESULT_INVALID) from exc
    return encoded


def _languages(texts: list[tuple[str, str | None]]) -> str:
    values = {language for _, language in texts if language}
    if not values:
        joined = "".join(text for text, _ in texts)
        if re.search(r"[\u4e00-\u9fff]", joined):
            values.add("zh")
        if re.search(r"[A-Za-z]", joined):
            values.add("en")
    return ",".join(sorted(values)) or "und"


class NativeOoxmlParser:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        source = await context.input(context.invocation.inputs[0].id)
        try:
            fixture = self._parse(source.content, source.reference.content_digest)
        except PluginError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise PluginError(PluginErrorCode.RESULT_INVALID) from exc
        content = _provider_bytes(fixture)
        languages = fixture["quality_signals"][1]["value"]  # type: ignore[index]
        return PluginInvocationResult(outputs=(PluginOutput(
            artifact_type="provider.native-ooxml-result", schema_revision="v1", content=content,
            summary="native OOXML parsed", metrics=(
                {"name": "source_bytes", "value": len(source.content)}, {"name": "page_count", "value": 1},
                {"name": "element_count", "value": len(fixture["elements"])},
            ), quality_signals=(
                {"name": "layout_detected", "status": "PASS", "value": "word_processing", "summary": "document paragraphs"},
                {"name": "languages_observed", "status": "PASS", "value": languages, "summary": "detected"},
            ),
        ),), summary="native OOXML parsed")

    @staticmethod
    def _parse(content: bytes, source_digest: str) -> dict[str, object]:
        if len(content) > MAX_SOURCE_BYTES:
            raise PluginError(PluginErrorCode.RESULT_INVALID)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ZIP_ENTRIES or sum(info.file_size for info in infos) > MAX_SOURCE_BYTES:
                raise ValueError("invalid OOXML archive")
            for info in infos:
                path = info.filename
                if path.startswith("/") or ".." in path.split("/") or info.flag_bits & 1 or info.file_size > MAX_XML_BYTES:
                    raise ValueError("unsafe OOXML archive member")
            content_types = _required_part(archive, "[Content_Types].xml")
            root_relationships = _required_part(archive, "_rels/.rels")
            document_xml = _required_part(archive, "word/document.xml")
        _validate_docx_package(content_types, root_relationships)
        if len(document_xml) > MAX_XML_BYTES:
            raise ValueError("DOCX document part too large")
        root = ElementTree.fromstring(document_xml)
        if root.tag != f"{_WORD_NS}document" or root.find(f"./{_WORD_NS}body") is None:
            raise ValueError("invalid WordprocessingML document root")
        elements: list[dict[str, object]] = []
        current_heading = "document"
        for paragraph_index, paragraph in enumerate(root.findall(f".//{_WORD_NS}p"), start=1):
            text = "".join(node.text or "" for node in paragraph.findall(f".//{_WORD_NS}t")).strip()
            if not text:
                continue
            style = paragraph.find(f"./{_WORD_NS}pPr/{_WORD_NS}pStyle")
            style_name = style.get(f"{_WORD_NS}val", "") if style is not None else ""
            heading = _HEADING.match(style_name)
            kind = "heading" if heading else "paragraph"
            if heading:
                current_heading = f"heading-{paragraph_index}"
            element: dict[str, object] = {"kind": kind, "reading_order": len(elements), "locator": {"kind": "word_processing", "heading_anchor": current_heading, "paragraph_index": paragraph_index}, "text": text}
            if heading:
                element["level"] = int(heading.group(1))
            elements.append(element)
        if not elements:
            raise ValueError("DOCX has no readable paragraphs")
        languages = _languages([(str(item["text"]), None) for item in elements])
        return {"adapter_id": "parser.native-ooxml@1", "source_content_digest": source_digest,
                "metadata": {"media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "language": languages.replace(",", "-")},
                "elements": elements, "quality_signals": (
                    {"name": "layout_detected", "status": "PASS", "value": "word_processing", "summary": "document paragraphs"},
                    {"name": "languages_observed", "status": "PASS", "value": languages, "summary": "detected"},
                )}


class LocalPdfParser:
    """Extract embedded PDF text locally into the typed provider fixture."""

    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        source = await context.input(context.invocation.inputs[0].id)
        try:
            fixture = self._parse(source.content, source.reference.content_digest)
        except PluginError:
            raise
        except (OSError, PdfReadError, ValueError) as exc:
            raise PluginError(PluginErrorCode.RESULT_INVALID) from exc
        content = _provider_bytes(fixture)
        languages = fixture["quality_signals"][1]["value"]  # type: ignore[index]
        return PluginInvocationResult(outputs=(PluginOutput(
            artifact_type="provider.parse-result-fixture", schema_revision="v1", content=content,
            summary="local PDF text extracted", metrics=(
                {"name": "source_bytes", "value": len(source.content)},
                {"name": "page_count", "value": len(fixture["elements"])},
                {"name": "element_count", "value": len(fixture["elements"])},
            ), quality_signals=(
                {"name": "layout_detected", "status": "PASS", "value": "pdf_page", "summary": "page text"},
                {"name": "languages_observed", "status": "PASS", "value": languages, "summary": "detected"},
            ),
        ),), summary="local PDF text extracted")

    @staticmethod
    def _parse(content: bytes, source_digest: str) -> dict[str, object]:
        if not content.startswith(b"%PDF-") or len(content) > MAX_PDF_SOURCE_BYTES:
            raise ValueError("invalid PDF source")
        reader = PdfReader(io.BytesIO(content), strict=True)
        if not reader.pages or len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError("PDF page count is unsupported")
        elements: list[dict[str, object]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text().strip()
            if not text:
                continue
            words = text[:MAX_PDF_PAGE_TEXT].split()
            for start in range(0, len(words), MAX_PDF_ELEMENT_TOKENS):
                if len(elements) == 4_096:
                    raise ValueError("PDF contains too many text segments")
                elements.append({
                    "kind": "paragraph", "reading_order": len(elements),
                    "locator": {"kind": "pdf", "page_number": page_number, "x0": 0, "y0": 0, "x1": 1, "y1": 1},
                    "text": " ".join(words[start:start + MAX_PDF_ELEMENT_TOKENS]),
                })
        if not elements:
            raise ValueError("PDF has no extractable text")
        languages = _languages([(str(item["text"]), None) for item in elements])
        return {
            "adapter_id": "parser.local-pdf@1", "source_content_digest": source_digest,
            "metadata": {"media_type": "application/pdf", "language": languages.replace(",", "-")},
            "elements": elements,
            "quality_signals": (
                {"name": "layout_detected", "status": "PASS", "value": "pdf_page", "summary": "page text"},
                {"name": "languages_observed", "status": "PASS", "value": languages, "summary": "detected"},
            ),
        }


def _required_part(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as exc:
        raise ValueError("required DOCX package part is missing") from exc


def _validate_docx_package(content_types: bytes, root_relationships: bytes) -> None:
    if len(content_types) > MAX_XML_BYTES or len(root_relationships) > MAX_XML_BYTES:
        raise ValueError("DOCX package part too large")
    content_root = ElementTree.fromstring(content_types)
    relationships_root = ElementTree.fromstring(root_relationships)
    expected_content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    has_document_override = any(
        item.get("PartName") == "/word/document.xml" and item.get("ContentType") == expected_content_type
        for item in content_root.findall(f"{_CONTENT_TYPES_NS}Override")
    )
    has_document_relationship = any(
        item.get("Type") == _OFFICE_DOCUMENT_RELATIONSHIP and item.get("Target") == "word/document.xml"
        for item in relationships_root.findall(f"{_RELATIONSHIPS_NS}Relationship")
    )
    if content_root.tag != f"{_CONTENT_TYPES_NS}Types" or relationships_root.tag != f"{_RELATIONSHIPS_NS}Relationships" or not has_document_override or not has_document_relationship:
        raise ValueError("invalid DOCX package relationships")


class ScannedOcrExchangeAdapter:
    async def invoke(self, context: PluginContext) -> PluginInvocationResult:
        source = await context.input(context.invocation.inputs[0].id)
        model_id = context.invocation.validated_configuration["model_id"]
        if model_id != "fixture-ocr-v1":
            raise PluginError(PluginErrorCode.UNAVAILABLE)
        try:
            if len(source.content) > MAX_SOURCE_BYTES:
                raise ValueError("OCR exchange too large")
            exchange = OcrExchange.model_validate_json(source.content)
            if exchange.model_id != model_id:
                raise PluginError(PluginErrorCode.UNAVAILABLE)
            fixture = self._fixture(exchange, source.reference.content_digest)
        except PluginError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise PluginError(PluginErrorCode.RESULT_INVALID) from exc
        content = _provider_bytes(fixture)
        languages = fixture["quality_signals"][1]["value"]  # type: ignore[index]
        confidence = fixture["quality_signals"][3]["value"]  # type: ignore[index]
        return PluginInvocationResult(outputs=(PluginOutput(
            artifact_type="provider.scanned-ocr-result", schema_revision="v1", content=content,
            summary="scanned OCR exchange converted", metrics=(
                {"name": "source_bytes", "value": len(source.content)}, {"name": "page_count", "value": len(exchange.pages)},
                {"name": "element_count", "value": sum(len(page.items) for page in exchange.pages)},
            ), quality_signals=(
                {"name": "layout_detected", "status": "PASS", "value": "scanned_page", "summary": "OCR exchange"},
                {"name": "languages_observed", "status": "PASS", "value": languages, "summary": "declared"},
                {"name": "ocr_model_id", "status": "PASS", "value": model_id, "summary": "allowlisted fixture model"},
                {"name": "ocr_confidence_bucket", "status": "PASS", "value": confidence, "summary": "bounded aggregate"},
            ),
        ),), summary="scanned OCR exchange converted")

    @staticmethod
    def _fixture(exchange: OcrExchange, source_digest: str) -> dict[str, object]:
        elements: list[dict[str, object]] = []
        scores: list[float] = []
        language_items: list[tuple[str, str | None]] = []
        for page in exchange.pages:
            for item in page.items:
                kind = "heading" if item.layout == "heading" else "paragraph"
                element: dict[str, object] = {"kind": kind, "reading_order": len(elements), "locator": {"kind": "pdf", "page_number": page.page_number, "x0": item.bbox[0], "y0": item.bbox[1], "x1": item.bbox[2], "y1": item.bbox[3]}, "text": item.text, "language": item.language,
                    "quality_signals": ({"name": "ocr_confidence", "status": "PASS" if item.confidence >= .8 else "WARN", "value": item.confidence, "summary": "recognized text"},)}
                if kind == "heading":
                    element["level"] = 1
                elements.append(element)
                scores.append(item.confidence)
                language_items.append((item.text, item.language))
        average = sum(scores) / len(scores)
        bucket = "high" if average >= .9 else "medium" if average >= .8 else "low"
        languages = _languages(language_items)
        return {"adapter_id": "ocr.scanned-exchange@1", "source_content_digest": source_digest,
                "metadata": {"media_type": "application/pdf", "language": languages.replace(",", "-")}, "elements": elements,
                "quality_signals": (
                    {"name": "layout_detected", "status": "PASS", "value": "scanned_page", "summary": "OCR exchange"},
                    {"name": "languages_observed", "status": "PASS", "value": languages, "summary": "declared"},
                    {"name": "ocr_model_id", "status": "PASS", "value": exchange.model_id, "summary": "allowlisted fixture model"},
                    {"name": "ocr_confidence_bucket", "status": "PASS", "value": bucket, "summary": "bounded aggregate"},
                )}
