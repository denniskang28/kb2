from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_sensitive_runtime_paths_are_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".runtime/" in ignored
    assert ".env.*" in ignored
    assert "*.pem" in ignored
    assert ".datasets/private/" in ignored


def test_runtime_files_contain_no_credential_assignment() -> None:
    runtime_files = [
        path
        for root in ("src", "deploy", "scripts", "tests")
        for path in (ROOT / root).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    forbidden = (
        "POSTGRES_" + "PASSWORD=",
        "DEEPSEEK_API_" + "KEY=",
        "AZURE_CLIENT_" + "SECRET=",
        "-----BEGIN PRIVATE " + "KEY-----",
    )
    for path in runtime_files:
        content = path.read_text(encoding="utf-8", errors="ignore")
        assert not any(pattern in content for pattern in forbidden), path


def test_compose_uses_file_mounted_secret_and_publishes_only_api() -> None:
    compose = (ROOT / "deploy/local/compose.yaml").read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD_FILE" in compose
    assert "DEEPSEEK_API_KEY_FILE" in compose
    assert "POSTGRES_PASSWORD:" not in compose
    assert "DEEPSEEK_API_KEY:" not in compose
    assert "ollama" not in compose.lower()
    assert "model-init" not in compose
    assert "docker.sock" not in compose
    assert compose.count("ports:") == 1
    assert '"127.0.0.1:${KB2_API_PORT:-8010}:8000"' in compose
    assert "azure" not in compose.lower()
