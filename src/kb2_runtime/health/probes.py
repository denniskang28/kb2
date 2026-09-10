from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg

from kb2_runtime.config import Settings


Probe = Callable[[], Awaitable[tuple[str, str]]]


async def bounded_probe(probe: Probe, timeout: float) -> tuple[str, str, int]:
    started = time.monotonic()
    try:
        status, code = await asyncio.wait_for(probe(), timeout=timeout)
    except asyncio.TimeoutError:
        status, code = "unavailable", "PROBE_TIMEOUT"
    except Exception:  # Probe boundaries deliberately suppress provider details.
        status, code = "unavailable", "DEPENDENCY_UNAVAILABLE"
    latency_ms = max(0, int((time.monotonic() - started) * 1000))
    return status, code, latency_ms


async def postgres_probe(settings: Settings) -> tuple[str, str]:
    async with await psycopg.AsyncConnection.connect(**settings.connection_kwargs()) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT 1")
            await cursor.fetchone()
    return "ready", "OK"


async def worker_probe(settings: Settings) -> tuple[str, str]:
    async with await psycopg.AsyncConnection.connect(**settings.connection_kwargs()) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - updated_at)) FROM runtime_worker_heartbeat WHERE worker_id = %s",
                ("default",),
            )
            row = await cursor.fetchone()
    if row is None or float(row[0]) > settings.heartbeat_freshness_seconds:
        return "unavailable", "HEARTBEAT_STALE"
    return "ready", "OK"


def _artifact_io(root: Path) -> None:
    health_dir = root / ".health"
    health_dir.mkdir(parents=True, exist_ok=True)
    target = health_dir / f"probe-{uuid4().hex}"
    try:
        target.write_bytes(b"ready")
        if target.read_bytes() != b"ready":
            raise OSError("artifact probe mismatch")
    finally:
        target.unlink(missing_ok=True)


async def artifact_probe(settings: Settings) -> tuple[str, str]:
    await asyncio.to_thread(_artifact_io, settings.artifact_root)
    return "ready", "OK"


async def deepseek_models(settings: Settings, api_key: str) -> set[str]:
    base_url = settings.trusted_deepseek_base_url()
    async with httpx.AsyncClient(
        timeout=settings.probe_timeout_seconds,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = await client.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        payload = response.json()
    models = payload.get("data", [])
    return {str(item.get("id", "")) for item in models if isinstance(item, dict)}
