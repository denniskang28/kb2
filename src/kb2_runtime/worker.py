from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import psycopg

from kb2_runtime.config import Settings


def log(event: str, severity: str = "INFO") -> None:
    print(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "severity": severity,
                "component": "worker",
                "eventCode": event,
            }
        ),
        flush=True,
    )


async def run() -> None:
    settings = Settings.from_env()
    log("WORKER_STARTED")
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(**settings.connection_kwargs()) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        """
                        INSERT INTO runtime_worker_heartbeat (worker_id, updated_at)
                        VALUES (%s, CURRENT_TIMESTAMP)
                        ON CONFLICT (worker_id) DO UPDATE SET updated_at = EXCLUDED.updated_at
                        """,
                        ("default",),
                    )
                await connection.commit()
        except Exception:
            log("HEARTBEAT_UPDATE_FAILED", "WARNING")
        await asyncio.sleep(settings.heartbeat_interval_seconds)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
