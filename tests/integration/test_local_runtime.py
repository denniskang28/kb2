from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from scripts.local_runtime import RuntimeOptions, ensure_state


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "local_runtime.py"
BASE_COMPOSE = ROOT / "deploy" / "local" / "compose.yaml"
TEST_OVERLAY = ROOT / "deploy" / "local" / "compose.test.yaml"
DEEPSEEK_OVERLAY = ROOT / "deploy" / "local" / "compose.deepseek-test.yaml"
CANARY = "CANARY-s001-password-private-provider-payload"
DEEPSEEK_CANARY = "CANARY-s001-deepseek-api-key"


def docker_available() -> bool:
    result = subprocess.run(
        ["docker", "info"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def cli_prefix(
    project: str, state: Path, port: int, extra_overlays: tuple[Path, ...] = ()
) -> list[str]:
    command = [
        sys.executable,
        str(CLI),
        "--project",
        project,
        "--environment",
        "test",
        "--state-root",
        str(state),
        "--compose-file",
        str(BASE_COMPOSE),
        "--overlay",
        str(TEST_OVERLAY),
    ]
    for overlay in extra_overlays:
        command.extend(("--overlay", str(overlay)))
    command.extend(
        [
            "--timeout",
            "120",
            "--api-port",
            str(port),
        ]
    )
    return command


def run(command: list[str], expected: int = 0, timeout: int = 480) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout
    )
    if result.returncode != expected:
        raise AssertionError(
            f"command failed with stable summary: exit={result.returncode} expected={expected} "
            f"stdout_lines={len(result.stdout.splitlines())} stderr={result.stderr.strip()}"
        )
    assert CANARY not in result.stdout
    assert CANARY not in result.stderr
    assert DEEPSEEK_CANARY not in result.stdout
    assert DEEPSEEK_CANARY not in result.stderr
    return result


def compose(
    project: str,
    state: Path,
    *args: str,
    overlays: tuple[Path, ...] = (),
    expected: int = 0,
) -> subprocess.CompletedProcess[str]:
    command = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(state / "compose.env"),
        "--file",
        str(BASE_COMPOSE),
        "--file",
        str(TEST_OVERLAY),
    ]
    for overlay in overlays:
        command.extend(("--file", str(overlay)))
    command.extend(args)
    return run(command, expected=expected)


def health(prefix: list[str], required: str | None = None, expected: int = 0) -> dict[str, object]:
    command = [*prefix, "health", "--json"]
    if required:
        command.extend(("--require", required))
    result = run(command, expected=expected)
    return json.loads(result.stdout)


def wait_ready(prefix: list[str], timeout: float = 40) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        result = subprocess.run(
            [*prefix, "health", "--json"], cwd=ROOT, capture_output=True, text=True, check=False
        )
        assert CANARY not in result.stdout
        assert CANARY not in result.stderr
        assert DEEPSEEK_CANARY not in result.stdout
        assert DEEPSEEK_CANARY not in result.stderr
        if result.stdout:
            last = json.loads(result.stdout)
        if result.returncode == 0:
            return last
        time.sleep(0.5)
    raise AssertionError(f"runtime did not recover; last_status={last.get('status', 'unknown')}")


def wait_component(
    prefix: list[str],
    component_id: str,
    status: str,
    codes: set[str],
    expected_exit: int,
    timeout: float = 30,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_status = "missing"
    last_code = "missing"
    last_exit = -1
    while time.monotonic() < deadline:
        result = subprocess.run(
            [*prefix, "health", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert CANARY not in result.stdout
        assert CANARY not in result.stderr
        assert DEEPSEEK_CANARY not in result.stdout
        assert DEEPSEEK_CANARY not in result.stderr
        last_exit = result.returncode
        if result.stdout:
            payload = json.loads(result.stdout)
            entry = next(
                (item for item in payload["components"] if item["id"] == component_id),
                None,
            )
            if entry is not None:
                last_status = str(entry["status"])
                last_code = str(entry["code"])
                if (
                    result.returncode == expected_exit
                    and last_status == status
                    and last_code in codes
                ):
                    return entry
        time.sleep(0.5)
    raise AssertionError(
        f"component did not reach expected state: id={component_id} "
        f"exit={last_exit} status={last_status} code={last_code}"
    )


def set_artifact_probe_writable(project: str, state: Path, writable: bool) -> None:
    mode = "0755" if writable else "0555"
    compose(
        project,
        state,
        "exec",
        "-T",
        "--user",
        "0:0",
        "api",
        "sh",
        "-c",
        f"mkdir -p /var/lib/kb2/artifacts/.health && "
        f"chown 10001:10001 /var/lib/kb2/artifacts/.health && "
        f"chmod {mode} /var/lib/kb2/artifacts/.health",
        overlays=(DEEPSEEK_OVERLAY,),
    )


def fixture_admin(project: str, state: Path, method: str, path: str) -> None:
    compose(
        project,
        state,
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        (
            "import urllib.request; "
            f"urllib.request.urlopen(urllib.request.Request('http://deepseek-fixture:8080{path}', "
            f"method='{method}')).read()"
        ),
        overlays=(DEEPSEEK_OVERLAY,),
    )


def prepare_canary_secret(project: str, state: Path, port: int) -> None:
    ensure_state(
        RuntimeOptions(
            project=project,
            environment="test",
            state_root=state,
            compose_files=(BASE_COMPOSE, TEST_OVERLAY),
            timeout=120,
            api_port=port,
        )
    )
    secret = state / "secrets" / "postgres_password"
    secret.write_text(CANARY, encoding="utf-8")
    secret.chmod(0o600)


def assert_no_project_resources(project: str) -> None:
    for resource, command in (
        ("containers", ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"]),
        ("volumes", ["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"]),
        ("networks", ["docker", "network", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"]),
    ):
        result = run(command)
        assert not result.stdout.strip(), f"target {resource} remain"


@pytest.mark.integration
def test_isolated_lifecycle_readiness_persistence_and_cleanup(tmp_path: Path) -> None:
    if not docker_available():
        pytest.skip("Docker daemon is unavailable")

    suffix = uuid.uuid4().hex[:8]
    project = f"kb2-it-{suffix}"
    other_project = f"kb2-it-other-{suffix}"
    state = tmp_path / project
    other_state = tmp_path / other_project
    port = free_port()
    other_port = free_port()
    prefix = cli_prefix(project, state, port)
    configured_prefix = cli_prefix(project, state, port, (DEEPSEEK_OVERLAY,))
    other_prefix = cli_prefix(other_project, other_state, other_port)
    prepare_canary_secret(project, state, port)
    prepare_canary_secret(other_project, other_state, other_port)

    try:
        run([*prefix, "up"])
        report = health(prefix)
        assert report["status"] == "ready"
        assert {entry["id"] for entry in report["components"]} == {
            "control.api",
            "metadata.postgres",
            "artifact.local",
            "worker.default",
        }
        entries = {entry["id"]: entry for entry in report["capabilities"]}
        assert entries["embedding.default"]["status"] == "not_configured"
        assert entries["generation.default"]["status"] == "not_configured"
        assert entries["generation.high_precision"]["status"] == "not_configured"
        services = compose(project, state, "config", "--services").stdout.splitlines()
        assert "deepseek-fixture" not in services

        selected = health(prefix, "generation.high_precision", expected=1)
        heavy = next(
            entry for entry in selected["capabilities"]
            if entry["id"] == "generation.high_precision"
        )
        assert heavy["required"] is True
        assert heavy["status"] == "not_configured"
        assert heavy["code"] == "NOT_CONFIGURED"

        compose(
            project,
            state,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "kb2",
            "-d",
            "kb2",
            "-c",
            "CREATE TABLE IF NOT EXISTS runtime_test_sentinel(value text); INSERT INTO runtime_test_sentinel VALUES ('preserved');",
        )
        compose(
            project,
            state,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "from pathlib import Path; Path('/var/lib/kb2/artifacts/persistence.txt').write_text('preserved')",
        )

        run([*prefix, "stop"])
        run([*prefix, "up"])
        database = compose(
            project,
            state,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "kb2",
            "-d",
            "kb2",
            "-Atc",
            "SELECT value FROM runtime_test_sentinel LIMIT 1",
        )
        artifact = compose(
            project,
            state,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "from pathlib import Path; print(Path('/var/lib/kb2/artifacts/persistence.txt').read_text())",
        )
        assert database.stdout.strip() == "preserved"
        assert artifact.stdout.strip() == "preserved"

        run([*prefix, "stop"])
        state.joinpath("secrets", "deepseek_api_key").write_text(
            DEEPSEEK_CANARY, encoding="utf-8"
        )
        state.joinpath("secrets", "deepseek_api_key").chmod(0o600)
        run([*configured_prefix, "up"])
        unprobed = health(configured_prefix)
        unprobed_entries = {
            entry["id"]: entry for entry in unprobed["capabilities"]
        }
        assert unprobed_entries["generation.default"]["status"] == "not_probed"
        assert unprobed_entries["generation.default"]["code"] == "NOT_PROBED"
        assert unprobed_entries["generation.high_precision"]["status"] == "not_probed"
        unprobed_log = compose(
            project,
            state,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import json,urllib.request; print(urllib.request.urlopen('http://deepseek-fixture:8080/test/requests').read().decode())",
            overlays=(DEEPSEEK_OVERLAY,),
        )
        assert json.loads(unprobed_log.stdout)["requests"] == []

        configured = health(configured_prefix, "generation.high_precision")
        configured_entries = {
            entry["id"]: entry for entry in configured["capabilities"]
        }
        assert configured_entries["generation.default"]["status"] == "not_probed"
        assert configured_entries["generation.default"]["code"] == "NOT_PROBED"
        assert configured_entries["generation.high_precision"]["status"] == "ready"
        assert configured_entries["embedding.default"]["status"] == "not_configured"

        fixture_admin(project, state, "DELETE", "/test/models/deepseek-v4-pro")
        missing = health(configured_prefix, "generation.high_precision", expected=1)
        missing_entry = next(
            entry for entry in missing["capabilities"]
            if entry["id"] == "generation.high_precision"
        )
        assert missing_entry["code"] == "MODEL_NOT_AVAILABLE"
        fixture_admin(project, state, "POST", "/test/models/deepseek-v4-pro")

        fixture_admin(project, state, "POST", "/test/failure/on")
        unavailable = health(configured_prefix, "generation.default", expected=1)
        unavailable_entry = next(
            entry for entry in unavailable["capabilities"]
            if entry["id"] == "generation.default"
        )
        assert unavailable_entry["code"] == "DEPENDENCY_UNAVAILABLE"
        fixture_admin(project, state, "POST", "/test/failure/off")
        assert health(configured_prefix, "generation.high_precision")["status"] == "ready"

        request_log = compose(
            project,
            state,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import json,urllib.request; print(urllib.request.urlopen('http://deepseek-fixture:8080/test/requests').read().decode())",
            overlays=(DEEPSEEK_OVERLAY,),
        )
        requests = json.loads(request_log.stdout)["requests"]
        assert requests
        assert all(item == {"path": "/models", "authenticated": True} for item in requests)
        configured_api_id = compose(
            project,
            state,
            "ps",
            "-q",
            "api",
            overlays=(DEEPSEEK_OVERLAY,),
        ).stdout.strip()
        run(["docker", "inspect", configured_api_id])
        compose(
            project,
            state,
            "logs",
            "api",
            "worker",
            "deepseek-fixture",
            overlays=(DEEPSEEK_OVERLAY,),
        )

        compose(project, state, "stop", "worker", overlays=(DEEPSEEK_OVERLAY,))
        worker_failure = wait_component(
            configured_prefix,
            "worker.default",
            "unavailable",
            {"HEARTBEAT_STALE"},
            expected_exit=1,
            timeout=30,
        )
        assert worker_failure["required"] is True
        compose(project, state, "start", "worker", overlays=(DEEPSEEK_OVERLAY,))
        assert wait_ready(configured_prefix)["status"] == "ready"

        set_artifact_probe_writable(project, state, False)
        try:
            artifact_failure = wait_component(
                configured_prefix,
                "artifact.local",
                "unavailable",
                {"DEPENDENCY_UNAVAILABLE", "PROBE_TIMEOUT"},
                expected_exit=1,
            )
            assert artifact_failure["required"] is True
        finally:
            set_artifact_probe_writable(project, state, True)
        assert wait_ready(configured_prefix)["status"] == "ready"

        compose(project, state, "stop", "postgres", overlays=(DEEPSEEK_OVERLAY,))
        failed = health(configured_prefix, expected=1)
        postgres = next(entry for entry in failed["components"] if entry["id"] == "metadata.postgres")
        assert postgres["status"] == "unavailable"
        assert postgres["code"] in {"DEPENDENCY_UNAVAILABLE", "PROBE_TIMEOUT"}
        compose(project, state, "start", "postgres", overlays=(DEEPSEEK_OVERLAY,))
        assert wait_ready(configured_prefix)["status"] == "ready"

        run([*other_prefix, "up"])
        run([*configured_prefix, "stop"])
        assert health(other_prefix)["status"] == "ready"

        logs = compose(other_project, other_state, "logs", "api", "worker").stdout
        assert CANARY not in logs
        assert DEEPSEEK_CANARY not in logs
        image = run(["docker", "image", "inspect", "kb2-runtime:0.1.0"]).stdout
        history = run(["docker", "history", "--no-trunc", "kb2-runtime:0.1.0"]).stdout
        assert CANARY not in image
        assert CANARY not in history
        image_payload = json.loads(image)[0]
        assert not any("PASSWORD=" in item for item in image_payload["Config"].get("Env", []))
        assert image_payload["Config"].get("User") == "10001:10001"

        api_id = compose(other_project, other_state, "ps", "-q", "api").stdout.strip()
        api_inspect = json.loads(run(["docker", "inspect", api_id]).stdout)[0]
        published = api_inspect["NetworkSettings"]["Ports"]
        assert published["8000/tcp"][0]["HostIp"] == "127.0.0.1"
        assert all("docker.sock" not in mount["Source"] for mount in api_inspect["Mounts"])
    finally:
        for active_prefix in (configured_prefix, other_prefix):
            subprocess.run(
                [*active_prefix, "clean", "--confirm", "kb2-local-data"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
            )

    assert not state.exists()
    assert not other_state.exists()
    assert_no_project_resources(project)
    assert_no_project_resources(other_project)
