from __future__ import annotations

import hashlib
import math
import re

from kb2_runtime.chunking.contracts import ChunkSet
from kb2_runtime.plugins.errors import PluginError, PluginErrorCode

from .contracts import DIMENSION, EmbeddingPort, EmbeddingRecord, EmbeddingSet
from .serializer import digest


TOKEN = re.compile(r"[a-z0-9]+")
HASHING_PLUGIN_ID = "embedder.hashing@1"
HASHING_IMPLEMENTATION_DIGEST = "3" * 64
HASHING_MODEL_ID = "local.feature-hash-256@1"


class HashingEmbedder:
    def embed_text(self, text: str) -> tuple[float, ...]:
        tokens = TOKEN.findall(" ".join(text.split()).lower())
        if not tokens:
            tokens = ["_"]
        values = [0.0] * DIMENSION
        for token in [*tokens, *(f"{left}\x1f{right}" for left, right in zip(tokens, tokens[1:]))]:
            raw = hashlib.sha256(token.encode("ascii")).digest()
            bucket = int.from_bytes(raw[:4], "big") % DIMENSION
            values[bucket] += 1.0 if raw[4] & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in values))
        return tuple(value / norm for value in values)


def embed_chunk_set(chunk_set: ChunkSet, implementation_digest: str = HASHING_IMPLEMENTATION_DIGEST) -> EmbeddingSet:
    try:
        source_digest = digest(chunk_set)
        embedder = HashingEmbedder()
        return EmbeddingSet(source_chunk_set_digest=source_digest, plugin_id=HASHING_PLUGIN_ID, implementation_digest=implementation_digest, model_id=HASHING_MODEL_ID, dimension=DIMENSION, records=tuple(EmbeddingRecord(chunk_id=chunk.chunk_id, values=embedder.embed_text(chunk.content)) for chunk in chunk_set.chunks))
    except (ValueError, TypeError) as exc:
        raise PluginError(PluginErrorCode.EMBEDDING_RECORD_INVALID) from exc
