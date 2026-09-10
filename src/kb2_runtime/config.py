from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(RuntimeError):
    """A stable, non-secret configuration failure."""


def _provider_base_url(environment: str, value: str) -> str:
    expected = (
        "http://deepseek-fixture:8080"
        if environment == "test"
        else "https://api.deepseek.com"
    )
    if value != expected:
        raise ConfigurationError("DEEPSEEK_BASE_URL_INVALID")
    return value


@dataclass(frozen=True)
class ComponentDefinition:
    id: str
    required: bool
    probe: str


@dataclass(frozen=True)
class CapabilityDefinition:
    id: str
    required: bool
    probe: str
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class Settings:
    environment: str
    postgres_provider: str
    artifact_provider: str
    deepseek_provider: str
    database_host: str
    database_port: int
    database_name: str
    database_user: str
    database_password_file: Path
    artifact_root: Path
    deepseek_base_url: str
    deepseek_api_key_file: Path
    capabilities_path: Path
    probe_timeout_seconds: float
    heartbeat_freshness_seconds: float
    heartbeat_interval_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("KB2_ENVIRONMENT", "local")
        default_catalog = Path("/app/deploy/local/capabilities.yaml")
        if not default_catalog.exists():
            default_catalog = Path.cwd() / "deploy" / "local" / "capabilities.yaml"
        return cls(
            environment=environment,
            postgres_provider=os.getenv("KB2_POSTGRES_PROVIDER", "postgres-pgvector-local"),
            artifact_provider=os.getenv("KB2_ARTIFACT_PROVIDER", "local-filesystem"),
            deepseek_provider=os.getenv("KB2_DEEPSEEK_PROVIDER", "deepseek"),
            database_host=os.getenv("KB2_DATABASE_HOST", "postgres"),
            database_port=int(os.getenv("KB2_DATABASE_PORT", "5432")),
            database_name=os.getenv("KB2_DATABASE_NAME", "kb2"),
            database_user=os.getenv("KB2_DATABASE_USER", "kb2"),
            database_password_file=Path(os.getenv("KB2_DATABASE_PASSWORD_FILE", "/run/secrets/postgres_password")),
            artifact_root=Path(os.getenv("KB2_ARTIFACT_ROOT", "/var/lib/kb2/artifacts")),
            deepseek_base_url=_provider_base_url(
                environment,
                os.getenv(
                    "KB2_DEEPSEEK_BASE_URL",
                    "http://deepseek-fixture:8080"
                    if environment == "test"
                    else "https://api.deepseek.com",
                ),
            ),
            deepseek_api_key_file=Path(
                os.getenv("KB2_DEEPSEEK_API_KEY_FILE", "/run/secrets/deepseek_api_key")
            ),
            capabilities_path=Path(os.getenv("KB2_CAPABILITIES_PATH", str(default_catalog))),
            probe_timeout_seconds=float(os.getenv("KB2_PROBE_TIMEOUT_SECONDS", "2")),
            heartbeat_freshness_seconds=float(os.getenv("KB2_HEARTBEAT_FRESHNESS_SECONDS", "10")),
            heartbeat_interval_seconds=float(os.getenv("KB2_HEARTBEAT_INTERVAL_SECONDS", "2")),
        )

    def database_password(self) -> str:
        try:
            return self.database_password_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigurationError("DATABASE_SECRET_UNAVAILABLE") from exc

    def connection_kwargs(self) -> dict[str, Any]:
        return {
            "host": self.database_host,
            "port": self.database_port,
            "dbname": self.database_name,
            "user": self.database_user,
            "password": self.database_password(),
        }

    def deepseek_api_key(self) -> str | None:
        try:
            value = self.deepseek_api_key_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigurationError("DEEPSEEK_SECRET_UNAVAILABLE") from exc
        return value or None

    def trusted_deepseek_base_url(self) -> str:
        return _provider_base_url(self.environment, self.deepseek_base_url)

    def safe_summary(self, catalog: "CapabilityCatalog") -> dict[str, Any]:
        return {
            "environment": self.environment,
            "providers": [self.postgres_provider, self.artifact_provider, self.deepseek_provider],
            "capabilities": [item.id for item in catalog.capabilities],
            "models": [item.model for item in catalog.capabilities if item.model is not None],
        }


@dataclass(frozen=True)
class CapabilityCatalog:
    components: tuple[ComponentDefinition, ...]
    capabilities: tuple[CapabilityDefinition, ...]

    @classmethod
    def load(cls, path: Path) -> "CapabilityCatalog":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            components = tuple(ComponentDefinition(**item) for item in raw["components"])
            capabilities = tuple(CapabilityDefinition(**item) for item in raw["capabilities"])
        except (OSError, KeyError, TypeError, yaml.YAMLError) as exc:
            raise ConfigurationError("CAPABILITY_CATALOG_INVALID") from exc
        ids = [item.id for item in (*components, *capabilities)]
        if len(ids) != len(set(ids)):
            raise ConfigurationError("CAPABILITY_ID_DUPLICATE")
        return cls(components=components, capabilities=capabilities)
