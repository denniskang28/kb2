from __future__ import annotations

from pathlib import Path

import pytest

from kb2_runtime.config import CapabilityCatalog, ConfigurationError, Settings


def test_safe_summary_contains_only_public_provider_and_capability_ids(
    settings: Settings, catalog: CapabilityCatalog
) -> None:
    canary = "CANARY-secret-provider-body"
    settings.database_password_file.write_text(canary, encoding="utf-8")

    summary = settings.safe_summary(catalog)

    encoded = str(summary)
    assert summary["environment"] == "test"
    assert summary["providers"] == [
        "postgres-pgvector-local",
        "local-filesystem",
        "deepseek",
    ]
    assert "embedding.default" in summary["capabilities"]
    assert summary["models"] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert canary not in encoded
    assert "database" not in encoded.lower()


def test_catalog_rejects_duplicate_ids(tmp_path: Path) -> None:
    catalog = tmp_path / "capabilities.yaml"
    catalog.write_text(
        """
components:
  - id: duplicate
    required: true
    probe: self
capabilities:
  - id: duplicate
    provider: local
    required: false
    probe: not-configured
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="CAPABILITY_ID_DUPLICATE"):
        CapabilityCatalog.load(catalog)


def test_missing_secret_maps_to_stable_code(settings: Settings) -> None:
    settings.database_password_file.unlink()

    with pytest.raises(ConfigurationError, match="DATABASE_SECRET_UNAVAILABLE"):
        settings.database_password()


def test_empty_deepseek_key_is_unconfigured(settings: Settings) -> None:
    assert settings.deepseek_api_key() is None


def test_missing_deepseek_key_maps_to_stable_code(settings: Settings) -> None:
    settings.deepseek_api_key_file.unlink()

    with pytest.raises(ConfigurationError, match="DEEPSEEK_SECRET_UNAVAILABLE"):
        settings.deepseek_api_key()


@pytest.mark.parametrize(
    ("environment", "base_url"),
    [
        ("local", "https://api.deepseek.com/"),
        ("local", "http://api.deepseek.com"),
        ("production", "https://api.deepseek.com/v1"),
        ("staging", "https://user:secret@api.deepseek.com"),
        ("staging", "https://api.deepseek.com?api_key=secret"),
        ("test", "https://api.deepseek.com"),
        ("test", "http://deepseek-fixture:8080/"),
        ("test", "http://other-fixture:8080"),
    ],
)
def test_deepseek_base_url_rejects_every_non_allowlisted_destination(
    environment: str, base_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KB2_ENVIRONMENT", environment)
    monkeypatch.setenv("KB2_DEEPSEEK_BASE_URL", base_url)

    with pytest.raises(ConfigurationError, match="DEEPSEEK_BASE_URL_INVALID"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("environment", "base_url"),
    [
        ("local", "https://api.deepseek.com"),
        ("production", "https://api.deepseek.com"),
        ("staging", "https://api.deepseek.com"),
        ("test", "http://deepseek-fixture:8080"),
    ],
)
def test_deepseek_base_url_accepts_only_environment_allowlist_pair(
    environment: str, base_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KB2_ENVIRONMENT", environment)
    monkeypatch.setenv("KB2_DEEPSEEK_BASE_URL", base_url)

    assert Settings.from_env().deepseek_base_url == base_url
