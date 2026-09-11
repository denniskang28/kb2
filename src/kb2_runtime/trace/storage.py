from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from .errors import TraceError, TraceErrorCode


class ArtifactStore:
    """Content-addressed immutable files rooted below the configured volume."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def locator(self, digest: str) -> str:
        self._validate_digest(digest)
        return f"sha256/{digest[:2]}/{digest}"

    def publish(self, content: bytes, digest: str, byte_size: int) -> str:
        self._validate_digest(digest)
        if len(content) != byte_size or hashlib.sha256(content).hexdigest() != digest:
            raise TraceError(TraceErrorCode.ARTIFACT_DIGEST_MISMATCH)
        destination = self._path_for(digest)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if destination.exists():
            self.read(digest, self.locator(digest))
            return self.locator(digest)
        descriptor, temporary = tempfile.mkstemp(prefix=".tmp-", dir=destination.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                self.read(digest, self.locator(digest))
            finally:
                Path(temporary).unlink(missing_ok=True)
        except OSError as exc:
            Path(temporary).unlink(missing_ok=True)
            raise TraceError(TraceErrorCode.TRACE_STORAGE_FAILURE) from exc
        return self.locator(digest)

    def read(self, digest: str, locator: str) -> bytes:
        if locator != self.locator(digest):
            raise TraceError(TraceErrorCode.ARTIFACT_CONTENT_MISSING)
        path = self._path_for(digest)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise TraceError(TraceErrorCode.ARTIFACT_CONTENT_MISSING) from exc
        if hashlib.sha256(content).hexdigest() != digest:
            raise TraceError(TraceErrorCode.ARTIFACT_DIGEST_MISMATCH)
        return content

    def _path_for(self, digest: str) -> Path:
        path = self.root / self.locator(digest)
        if self.root not in path.resolve().parents:
            raise TraceError(TraceErrorCode.ARTIFACT_CONTENT_MISSING)
        return path

    @staticmethod
    def _validate_digest(digest: str) -> None:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise TraceError(TraceErrorCode.ARTIFACT_DIGEST_MISMATCH)
