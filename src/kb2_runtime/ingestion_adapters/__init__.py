"""Bounded, deterministic representative ingestion plugin implementations."""

from .adapters import LocalPdfParser, NativeOoxmlParser, OcrExchangeConfig, ScannedOcrExchangeAdapter

__all__ = ("LocalPdfParser", "NativeOoxmlParser", "OcrExchangeConfig", "ScannedOcrExchangeAdapter")
