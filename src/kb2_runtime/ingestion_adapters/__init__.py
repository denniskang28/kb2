"""Bounded, deterministic representative ingestion plugin implementations."""

from .adapters import NativeOoxmlParser, OcrExchangeConfig, ScannedOcrExchangeAdapter

__all__ = ("NativeOoxmlParser", "OcrExchangeConfig", "ScannedOcrExchangeAdapter")
