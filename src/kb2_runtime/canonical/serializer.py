from __future__ import annotations

import hashlib
import json

from .contracts import CanonicalDocument, Locator


def stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:32]}"


def locator_key(locator: Locator) -> str:
    return json.dumps(locator.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def canonical_document_bytes(document: CanonicalDocument) -> bytes:
    return json.dumps(document.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
