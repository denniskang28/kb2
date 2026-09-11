from __future__ import annotations

from enum import StrEnum


class CanonicalErrorCode(StrEnum):
    INPUT_INVALID = "CANONICAL_INPUT_INVALID"
    DOCUMENT_INVALID = "CANONICAL_DOCUMENT_INVALID"
    FIELD_UNBOUNDED = "CANONICAL_FIELD_UNBOUNDED"


class CanonicalError(ValueError):
    """Safe validation failure; location is deliberately bounded and payload-free."""

    def __init__(self, code: CanonicalErrorCode, location: str = "$") -> None:
        super().__init__(code.value)
        self.code = code
        self.location = location[:128]
