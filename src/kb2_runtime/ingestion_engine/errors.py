from __future__ import annotations

from enum import StrEnum


class IngestionErrorCode(StrEnum):
    SOURCE_SCHEMA_MISMATCH = "SOURCE_SCHEMA_MISMATCH"
    PLAN_IMPLEMENTATION_DRIFT = "PLAN_IMPLEMENTATION_DRIFT"
    STAGE_EXHAUSTED = "STAGE_EXHAUSTED"
    OUTPUT_INVALID = "OUTPUT_INVALID"


class IngestionError(RuntimeError):
    def __init__(self, code: IngestionErrorCode) -> None:
        super().__init__(code.value)
        self.code = code
