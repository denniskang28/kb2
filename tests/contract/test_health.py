from __future__ import annotations

import asyncio
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

import kb2_runtime.health.probes as probe_module
import kb2_runtime.health.service as health_module
from kb2_runtime.api import create_app
from kb2_runtime.config import CapabilityCatalog, ConfigurationError, Settings
from kb2_runtime.health.probes import bounded_probe, deepseek_models
from kb2_runtime.health.service import HealthService, UnknownCapabilityError


async def ready_probe(_: Settings) -> tuple[str, str]:
    return "ready", "OK"


@pytest.fixture
def core_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "postgres_probe", ready_probe)
    monkeypatch.setattr(health_module, "artifact_probe", ready_probe)
    monkeypatch.setattr(health_module, "worker_probe", ready_probe)


def test_liveness_has_no_dependency_on_readiness(
    settings: Settings, catalog: CapabilityCatalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def explode(_: Settings) -> tuple[str, str]:
        raise RuntimeError("CANARY-secret-provider-body")

    monkeypatch.setattr(health_module, "postgres_probe", explode)
    response = TestClient(create_app(settings, catalog)).get("/health/live")

    assert response.status_code == 200
    assert response.json()["contractVersion"] == "health/v1"
    assert response.json()["live"] is True


def test_no_key_core_is_ready_and_all_model_capabilities_are_not_configured(
    settings: Settings,
    catalog: CapabilityCatalog,
    core_ready: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden(*_: object) -> set[str]:
        raise AssertionError("no external request is permitted without a key")

    monkeypatch.setattr(health_module, "deepseek_models", forbidden)
    response = TestClient(create_app(settings, catalog)).get("/health/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert [item["id"] for item in payload["components"]] == [item.id for item in catalog.components]
    assert [item["id"] for item in payload["capabilities"]] == [item.id for item in catalog.capabilities]
    for capability_id in (
        "embedding.default",
        "generation.default",
        "generation.high_precision",
        "runner.container",
    ):
        entry = next(item for item in payload["capabilities"] if item["id"] == capability_id)
        assert entry["status"] == "not_configured"
        assert entry["required"] is False


def test_no_key_generation_only_blocks_an_experiment_that_requires_it(
    settings: Settings, catalog: CapabilityCatalog, core_ready: None
) -> None:
    client = TestClient(create_app(settings, catalog))

    default = client.get("/health/ready")
    selected = client.get(
        "/health/capabilities", params={"require": "generation.high_precision"}
    )

    assert default.status_code == 200
    assert selected.status_code == 503
    high_precision = next(
        item for item in selected.json()["capabilities"]
        if item["id"] == "generation.high_precision"
    )
    assert high_precision["required"] is True
    assert high_precision["status"] == "not_configured"
    assert high_precision["code"] == "NOT_CONFIGURED"
    assert high_precision["model"] == "deepseek-v4-pro"


def test_configured_but_unrequested_generation_is_not_probed(
    settings: Settings,
    catalog: CapabilityCatalog,
    core_ready: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.deepseek_api_key_file.write_text("configured-key", encoding="utf-8")

    async def forbidden(*_: object) -> set[str]:
        raise AssertionError("plain capability health must not call DeepSeek")

    monkeypatch.setattr(health_module, "deepseek_models", forbidden)
    response = TestClient(create_app(settings, catalog)).get("/health/capabilities")

    assert response.status_code == 200
    entries = {item["id"]: item for item in response.json()["capabilities"]}
    assert entries["generation.default"]["status"] == "not_probed"
    assert entries["generation.default"]["code"] == "NOT_PROBED"
    assert entries["generation.high_precision"]["status"] == "not_probed"
    assert entries["embedding.default"]["status"] == "not_configured"
    assert "provider" not in entries["embedding.default"]


def test_explicit_generation_requirements_share_one_inventory_for_exact_models(
    settings: Settings,
    catalog: CapabilityCatalog,
    core_ready: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.deepseek_api_key_file.write_text("CANARY-api-key", encoding="utf-8")
    calls = 0

    async def inventory(_: Settings, api_key: str) -> set[str]:
        nonlocal calls
        calls += 1
        assert api_key == "CANARY-api-key"
        return {"deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-preview"}

    monkeypatch.setattr(health_module, "deepseek_models", inventory)
    response = TestClient(create_app(settings, catalog)).get(
        "/health/capabilities",
        params=[
            ("require", "generation.default"),
            ("require", "generation.high_precision"),
        ],
    )

    assert response.status_code == 200
    assert calls == 1
    assert "CANARY-api-key" not in response.text
    entries = {item["id"]: item for item in response.json()["capabilities"]}
    assert entries["generation.default"]["status"] == "ready"
    assert entries["generation.default"]["model"] == "deepseek-v4-flash"
    assert entries["generation.high_precision"]["status"] == "ready"


def test_missing_exact_model_is_reported_without_breaking_optional_core(
    settings: Settings,
    catalog: CapabilityCatalog,
    core_ready: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.deepseek_api_key_file.write_text("configured-key", encoding="utf-8")

    async def inventory(_: Settings, __: str) -> set[str]:
        return {"deepseek-v4-flash", "deepseek-v4-pro-preview"}

    monkeypatch.setattr(health_module, "deepseek_models", inventory)
    client = TestClient(create_app(settings, catalog))

    optional = client.get("/health/capabilities")
    required = client.get(
        "/health/capabilities", params={"require": "generation.high_precision"}
    )

    assert optional.status_code == 200
    optional_entry = next(
        item for item in optional.json()["capabilities"]
        if item["id"] == "generation.high_precision"
    )
    assert optional_entry["status"] == "not_probed"
    assert required.status_code == 503
    entry = next(
        item for item in required.json()["capabilities"]
        if item["id"] == "generation.high_precision"
    )
    assert entry["code"] == "MODEL_NOT_AVAILABLE"


def test_provider_error_is_sanitized_and_only_blocks_required_generation(
    settings: Settings,
    catalog: CapabilityCatalog,
    core_ready: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "CANARY-provider-response-with-key"
    settings.deepseek_api_key_file.write_text("configured-key", encoding="utf-8")

    async def unavailable(_: Settings, __: str) -> set[str]:
        raise RuntimeError(canary)

    monkeypatch.setattr(health_module, "deepseek_models", unavailable)
    client = TestClient(create_app(settings, catalog))

    optional = client.get("/health/capabilities")
    required = client.get(
        "/health/capabilities", params={"require": "generation.default"}
    )

    assert optional.status_code == 200
    optional_entry = next(
        item for item in optional.json()["capabilities"]
        if item["id"] == "generation.default"
    )
    assert optional_entry["status"] == "not_probed"
    assert required.status_code == 503
    encoded = required.text
    entry = next(
        item for item in required.json()["capabilities"]
        if item["id"] == "generation.default"
    )
    assert entry["code"] == "DEPENDENCY_UNAVAILABLE"
    assert canary not in encoded


def test_core_ready_never_probes_external_provider_even_with_key(
    settings: Settings,
    catalog: CapabilityCatalog,
    core_ready: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.deepseek_api_key_file.write_text("configured-key", encoding="utf-8")

    async def forbidden(*_: object) -> set[str]:
        raise AssertionError("core readiness must not call DeepSeek")

    monkeypatch.setattr(health_module, "deepseek_models", forbidden)
    response = TestClient(create_app(settings, catalog)).get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_unknown_required_capability_is_rejected(
    settings: Settings, catalog: CapabilityCatalog, core_ready: None
) -> None:
    response = TestClient(create_app(settings, catalog)).get(
        "/health/capabilities", params={"require": "unknown.capability"}
    )

    assert response.status_code == 400
    assert response.json() == {
        "contractVersion": "health/v1",
        "code": "UNKNOWN_CAPABILITY",
        "unknown": ["unknown.capability"],
    }


def test_probe_timeout_and_exception_are_sanitized() -> None:
    canary = "CANARY-password-and-provider-response"

    async def slow() -> tuple[str, str]:
        await asyncio.sleep(0.05)
        return "ready", "OK"

    async def broken() -> tuple[str, str]:
        raise RuntimeError(canary)

    timeout = asyncio.run(bounded_probe(slow, 0.001))
    failure = asyncio.run(bounded_probe(broken, 0.1))

    assert timeout[:2] == ("unavailable", "PROBE_TIMEOUT")
    assert failure[:2] == ("unavailable", "DEPENDENCY_UNAVAILABLE")
    assert canary not in str((timeout, failure))


def test_deepseek_probe_only_calls_authenticated_models_endpoint(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"data": [{"id": "deepseek-v4-flash"}, {"id": "other"}]},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    client_options: list[dict[str, object]] = []

    def client(**options: object) -> httpx.AsyncClient:
        client_options.append(options)
        return real_client(transport=transport)

    monkeypatch.setattr(
        probe_module.httpx,
        "AsyncClient",
        client,
    )

    models = asyncio.run(deepseek_models(settings, "CANARY-api-key"))

    assert models == {"deepseek-v4-flash", "other"}
    assert len(requests) == 1
    assert requests[0].url.path == "/models"
    assert requests[0].headers["Authorization"] == "Bearer CANARY-api-key"
    assert "chat" not in requests[0].url.path
    assert client_options == [
        {
            "timeout": settings.probe_timeout_seconds,
            "follow_redirects": False,
            "trust_env": False,
        }
    ]


def test_deepseek_probe_does_not_follow_redirect_or_inherit_proxy(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[httpx.Request] = []
    options_seen: list[dict[str, object]] = []

    async def redirect(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://attacker.invalid/models"})

    transport = httpx.MockTransport(redirect)
    real_client = httpx.AsyncClient

    def client(**options: object) -> httpx.AsyncClient:
        options_seen.append(options)
        return real_client(
            transport=transport,
            follow_redirects=bool(options["follow_redirects"]),
            trust_env=bool(options["trust_env"]),
        )

    monkeypatch.setenv("HTTPS_PROXY", "http://attacker.invalid:8080")
    monkeypatch.setattr(probe_module.httpx, "AsyncClient", client)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(deepseek_models(settings, "CANARY-api-key"))

    assert len(requests) == 1
    assert requests[0].url.host == "deepseek-fixture"
    assert options_seen[0]["follow_redirects"] is False
    assert options_seen[0]["trust_env"] is False


def test_deepseek_probe_revalidates_destination_before_receiving_key(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    unsafe_settings = replace(settings, deepseek_base_url="http://attacker.invalid")

    def forbidden_client(**_: object) -> object:
        raise AssertionError("untrusted destination must be rejected before client creation")

    monkeypatch.setattr(probe_module.httpx, "AsyncClient", forbidden_client)

    with pytest.raises(ConfigurationError, match="DEEPSEEK_BASE_URL_INVALID"):
        asyncio.run(deepseek_models(unsafe_settings, "CANARY-api-key"))


def test_unknown_capability_error_is_deterministic(
    settings: Settings, catalog: CapabilityCatalog
) -> None:
    with pytest.raises(UnknownCapabilityError) as error:
        asyncio.run(HealthService(settings, catalog).report(("z", "a", "z")))

    assert error.value.unknown == ["a", "z"]
