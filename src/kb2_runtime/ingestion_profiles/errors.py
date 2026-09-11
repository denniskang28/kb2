from __future__ import annotations

from enum import StrEnum


class ProfileErrorCode(StrEnum):
    PARSE_INVALID = "PROFILE_PARSE_INVALID"
    UNSAFE_CONTENT = "PROFILE_UNSAFE_CONTENT"
    PLUGIN_UNKNOWN = "PROFILE_PLUGIN_UNKNOWN"
    PLUGIN_UNAVAILABLE = "PROFILE_PLUGIN_UNAVAILABLE"
    CONFIGURATION_INVALID = "PROFILE_CONFIGURATION_INVALID"
    PORT_UNBOUND = "PROFILE_PORT_UNBOUND"
    SCHEMA_INCOMPATIBLE = "PROFILE_SCHEMA_INCOMPATIBLE"
    GRAPH_CYCLE = "PROFILE_GRAPH_CYCLE"
    CONDITION_UNSUPPORTED = "PROFILE_CONDITION_UNSUPPORTED"
    SELECTION_INVALID = "PROFILE_SELECTION_INVALID"


class ProfileError(ValueError):
    def __init__(self, code: ProfileErrorCode, location: str = "/") -> None:
        self.code, self.location = code, location[:256]
        super().__init__(f"{code.value} at {self.location}")
