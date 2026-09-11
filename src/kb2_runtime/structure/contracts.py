from enum import StrEnum

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StructureStrategy(StrEnum):
    HIERARCHY = "hierarchy"
    LAYOUT = "layout"
    TABLE = "table"


class StructureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Keep the generated Plugin descriptor reference-free; the Registry rejects
    # JSON Schema $ref to prevent indirection in declarative configuration.
    strategy: Literal["hierarchy", "layout", "table"]
