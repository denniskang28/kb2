from __future__ import annotations

import json

from .contracts import ChunkSet


def chunk_set_bytes(chunk_set: ChunkSet) -> bytes:
    return json.dumps(chunk_set.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
