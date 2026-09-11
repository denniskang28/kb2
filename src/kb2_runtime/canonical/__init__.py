"""Provider-neutral CanonicalDocument/v1 contracts and normalizer."""

from .contracts import CanonicalDocument, ProviderFixture
from .serializer import canonical_document_bytes

__all__ = ("CanonicalDocument", "ProviderFixture", "canonical_document_bytes")
