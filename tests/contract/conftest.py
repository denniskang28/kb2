from __future__ import annotations

from pathlib import Path

import pytest

from kb2_runtime.config import CapabilityCatalog, Settings


@pytest.fixture
def catalog() -> CapabilityCatalog:
    return CapabilityCatalog.load(Path("deploy/local/capabilities.yaml"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    secret = tmp_path / "password"
    secret.write_text("test-only-password", encoding="utf-8")
    deepseek_key = tmp_path / "deepseek-key"
    deepseek_key.write_text("", encoding="utf-8")
    return Settings(
        environment="test",
        postgres_provider="postgres-pgvector-local",
        artifact_provider="local-filesystem",
        deepseek_provider="deepseek",
        database_host="postgres",
        database_port=5432,
        database_name="kb2",
        database_user="kb2",
        database_password_file=secret,
        artifact_root=tmp_path / "artifacts",
        deepseek_base_url="http://deepseek-fixture:8080",
        deepseek_api_key_file=deepseek_key,
        capabilities_path=Path("deploy/local/capabilities.yaml"),
        probe_timeout_seconds=0.1,
        heartbeat_freshness_seconds=10,
        heartbeat_interval_seconds=2,
    )
