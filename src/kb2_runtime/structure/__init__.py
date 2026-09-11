"""Deterministic CanonicalDocument structure preservation."""

from .contracts import StructureConfig, StructureStrategy
from .plugin import CanonicalStructurePlugin

__all__ = ("CanonicalStructurePlugin", "StructureConfig", "StructureStrategy")
