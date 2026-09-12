from __future__ import annotations

import json
import math
import re
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from kb2_runtime.trace.contracts import metadata_contains_sensitive_text

from .contracts import QueryProfileSet
from .errors import QueryProfileError, QueryProfileErrorCode

_FORBIDDEN = re.compile(r"(?:command|script|path|credential|secret|environment|entrypoint|image|mount|executable)", re.I)


class _NoDuplicateLoader(yaml.SafeLoader):
    pass


def _mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise yaml.constructor.ConstructorError(None, None, "invalid mapping key", key_node.start_mark)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_NoDuplicateLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


class QueryProfileParser:
    @staticmethod
    def parse(source: str | bytes, media_type: Literal["application/json", "application/yaml"]) -> QueryProfileSet:
        try:
            raw = source.decode("utf-8") if isinstance(source, bytes) else source
            if len(raw.encode()) > 64 * 1024:
                raise ValueError
            if media_type == "application/json":
                value = json.loads(raw, object_pairs_hook=_json_object, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            elif media_type == "application/yaml" and not re.search(r"(?:!|&|\*|<<:)", raw):
                value = yaml.load(raw, Loader=_NoDuplicateLoader)
            else:
                raise ValueError
        except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError):
            raise QueryProfileError(QueryProfileErrorCode.PARSE_INVALID) from None
        if not isinstance(value, dict):
            raise QueryProfileError(QueryProfileErrorCode.PARSE_INVALID)
        if _unsafe(value):
            raise QueryProfileError(QueryProfileErrorCode.UNSAFE_CONTENT)
        try:
            return QueryProfileSet.model_validate(value)
        except ValidationError as exc:
            raise QueryProfileError(QueryProfileErrorCode.PARSE_INVALID, "/" + "/".join(map(str, exc.errors()[0]["loc"]))) from None


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _unsafe(value: object, depth: int = 0) -> bool:
    if depth > 16:
        return True
    if isinstance(value, str):
        return "${" in value or metadata_contains_sensitive_text(value)
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_FORBIDDEN.search(str(key)) or _unsafe(item, depth + 1) for key, item in value.items())
    if isinstance(value, list):
        return len(value) > 128 or any(_unsafe(item, depth + 1) for item in value)
    return not isinstance(value, (int, float, bool, type(None)))
