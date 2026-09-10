from __future__ import annotations

import json
import socket
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.local_runtime import (
    CLEAN_CONFIRMATION,
    RuntimeFailure,
    RuntimeOptions,
    command_clean,
    command_up,
    compose_command,
    ensure_state,
    main,
    preflight,
    unavailable_report,
    validate_project,
    validate_state_root,
)


def options(tmp_path: Path) -> RuntimeOptions:
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text("services: {}", encoding="utf-8")
    return RuntimeOptions(
        project="kb2-test-project",
        environment="test",
        state_root=tmp_path / "kb2-test-project",
        compose_files=(compose_file,),
        timeout=10,
        api_port=18010,
    )


@pytest.mark.parametrize("project", ["KB2", "-bad", "ab", "bad_name", "bad name"])
def test_project_name_rejects_unsafe_values(project: str) -> None:
    with pytest.raises(RuntimeFailure, match="PROJECT_NAME_INVALID"):
        validate_project(project)


def test_state_root_rejects_broad_paths() -> None:
    for path in (Path("/"), Path.home(), Path.cwd(), Path.cwd().parent):
        with pytest.raises(RuntimeFailure, match="STATE_ROOT_UNSAFE"):
            validate_state_root(path)


def test_secret_is_generated_with_restrictive_mode_and_never_put_in_compose_args(tmp_path: Path) -> None:
    runtime = options(tmp_path)

    ensure_state(runtime)

    secret = runtime.secret_path.read_text(encoding="utf-8")
    assert secret
    assert runtime.secret_path.stat().st_mode & 0o777 == 0o600
    assert secret not in " ".join(compose_command(runtime, "up"))
    assert secret not in runtime.env_path.read_text(encoding="utf-8")
    assert str(runtime.secret_path) in runtime.env_path.read_text(encoding="utf-8")
    assert runtime.deepseek_key_path.read_text(encoding="utf-8") == ""
    assert runtime.deepseek_key_path.stat().st_mode & 0o777 == 0o600
    assert str(runtime.deepseek_key_path) in runtime.env_path.read_text(encoding="utf-8")
    assert runtime.marker_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(runtime.marker_path.read_text(encoding="utf-8")) == {
        "contractVersion": "kb2-runtime-state/v1",
        "project": runtime.project,
        "root": str(runtime.state_root.resolve()),
    }


def test_populated_deepseek_key_must_have_exact_private_mode(tmp_path: Path) -> None:
    runtime = options(tmp_path)
    ensure_state(runtime)
    runtime.deepseek_key_path.write_text("CANARY-deepseek-key", encoding="utf-8")
    runtime.deepseek_key_path.chmod(0o644)

    with pytest.raises(RuntimeFailure, match="DEEPSEEK_KEY_FILE_PERMISSIONS_INVALID"):
        ensure_state(runtime)

    assert "CANARY-deepseek-key" not in runtime.env_path.read_text(encoding="utf-8")


def test_existing_custom_unowned_state_root_is_rejected(tmp_path: Path) -> None:
    runtime = options(tmp_path)
    runtime.state_root.mkdir()
    sentinel = runtime.state_root / "user-content"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(RuntimeFailure, match="STATE_ROOT_UNOWNED"):
        ensure_state(runtime)

    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_existing_empty_custom_state_root_is_rejected(tmp_path: Path) -> None:
    runtime = options(tmp_path)
    runtime.state_root.mkdir()

    with pytest.raises(RuntimeFailure, match="STATE_ROOT_UNOWNED"):
        ensure_state(runtime)


def test_state_root_must_be_a_directory(tmp_path: Path) -> None:
    runtime = options(tmp_path)
    runtime.state_root.write_text("not-a-directory", encoding="utf-8")

    with pytest.raises(RuntimeFailure, match="STATE_ROOT_INVALID"):
        ensure_state(runtime)


def test_exact_default_empty_root_can_be_claimed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = replace(options(tmp_path), state_root=tmp_path / ".runtime" / "kb2-test-project")
    runtime.state_root.mkdir(parents=True)
    monkeypatch.setattr("scripts.local_runtime.ROOT", tmp_path)

    ensure_state(runtime)
    ensure_state(runtime)

    assert runtime.marker_path.is_file()


def test_main_rejects_default_leaf_symlink_without_touching_target_or_compose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = "kb2-test-project"
    external = tmp_path / "external-default-target"
    external.mkdir()
    runtime_parent = tmp_path / ".runtime"
    runtime_parent.mkdir()
    (runtime_parent / project).symlink_to(external, target_is_directory=True)
    monkeypatch.setattr("scripts.local_runtime.ROOT", tmp_path)
    monkeypatch.setattr(
        "scripts.local_runtime.run_checked",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("invalid state root must be rejected before Compose")
        ),
    )

    assert main(["--project", project, "up"]) == 2

    assert capsys.readouterr().err.strip() == "status=failed code=STATE_ROOT_INVALID"
    assert list(external.iterdir()) == []


@pytest.mark.parametrize("symlink_kind", ["parent", "leaf"])
def test_main_rejects_custom_symlink_component_without_touching_target_or_compose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    symlink_kind: str,
) -> None:
    external = tmp_path / f"external-{symlink_kind}-target"
    external.mkdir()
    if symlink_kind == "parent":
        linked_parent = tmp_path / "linked-parent"
        linked_parent.symlink_to(external, target_is_directory=True)
        state_root = linked_parent / "project-state"
    else:
        state_root = tmp_path / "linked-state"
        state_root.symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(
        "scripts.local_runtime.run_checked",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("invalid state root must be rejected before Compose")
        ),
    )

    assert main(["--state-root", str(state_root), "up"]) == 2

    assert capsys.readouterr().err.strip() == "status=failed code=STATE_ROOT_INVALID"
    assert list(external.iterdir()) == []


def test_compose_command_is_scoped_to_exact_project(tmp_path: Path) -> None:
    runtime = options(tmp_path)
    ensure_state(runtime)

    command = compose_command(runtime, "down", "--remove-orphans")

    assert command[:4] == ["docker", "compose", "--project-name", "kb2-test-project"]
    assert "--volumes" not in command
    assert command[-2:] == ["down", "--remove-orphans"]


def test_up_waits_on_core_readiness_without_capability_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = options(tmp_path)
    requests: list[tuple[tuple[str, ...], bool]] = []

    monkeypatch.setattr("scripts.local_runtime.ensure_state", lambda _: None)
    monkeypatch.setattr("scripts.local_runtime.preflight", lambda _: None)
    monkeypatch.setattr(
        "scripts.local_runtime.run_checked",
        lambda *args, **kwargs: SimpleNamespace(stdout=""),
    )

    def ready(
        _: RuntimeOptions,
        required: tuple[str, ...],
        *,
        capabilities: bool = True,
    ) -> tuple[int, dict[str, str]]:
        requests.append((required, capabilities))
        return 200, {"environment": "test", "status": "ready"}

    monkeypatch.setattr("scripts.local_runtime.fetch_health", ready)
    monkeypatch.setattr("scripts.local_runtime.print_health", lambda *args: None)

    assert command_up(runtime) == 0
    assert requests == [((), False)]


def test_preflight_tolerates_transient_port_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    runtime = replace(options(tmp_path), api_port=listener.getsockname()[1])
    sleep_calls = 0

    def release_listener(_: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        listener.close()

    monkeypatch.setattr("scripts.local_runtime.run_checked", lambda *args, **kwargs: SimpleNamespace(stdout=""))
    monkeypatch.setattr("scripts.local_runtime.time.sleep", release_listener)

    try:
        preflight(runtime)
    finally:
        listener.close()

    assert sleep_calls == 1


def test_preflight_returns_immediately_when_project_api_is_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = options(tmp_path)
    calls = 0

    def running_project(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        return SimpleNamespace(stdout="container-id\n" if calls == 2 else "")

    monkeypatch.setattr("scripts.local_runtime.run_checked", running_project)

    def unexpected_socket() -> object:
        raise AssertionError("a running project must bypass host-port probing")

    monkeypatch.setattr("scripts.local_runtime.socket.socket", unexpected_socket)

    preflight(runtime)

    assert calls == 2


def test_preflight_rejects_sustained_port_conflict_with_sanitized_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    runtime = replace(options(tmp_path), api_port=listener.getsockname()[1])

    monkeypatch.setattr("scripts.local_runtime.run_checked", lambda *args, **kwargs: SimpleNamespace(stdout=""))
    monkeypatch.setattr("scripts.local_runtime.PORT_RELEASE_WAIT_SECONDS", 0.0)

    try:
        with pytest.raises(RuntimeFailure) as error:
            preflight(runtime)
    finally:
        listener.close()

    assert str(error.value) == "API_PORT_UNAVAILABLE"
    assert error.value.__cause__ is None


def test_clean_requires_confirmation_before_running_compose(tmp_path: Path) -> None:
    runtime = options(tmp_path)
    ensure_state(runtime)

    with pytest.raises(RuntimeFailure, match="CLEAN_CONFIRMATION_REQUIRED"):
        command_clean(runtime, "wrong")

    assert runtime.state_root.exists()
    assert CLEAN_CONFIRMATION == "kb2-local-data"


def test_clean_removes_only_owned_marked_state_after_scoped_compose_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = options(tmp_path)
    ensure_state(runtime)
    commands: list[list[str]] = []

    def record(command: list[str], *_: object, **__: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("scripts.local_runtime.run_checked", record)

    assert command_clean(runtime, CLEAN_CONFIRMATION) == 0

    assert not runtime.state_root.exists()
    assert len(commands) == 1
    assert commands[0][-3:] == ["down", "--volumes", "--remove-orphans"]
    assert "--project-name" in commands[0]
    assert runtime.project in commands[0]


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("malformed", "STATE_MARKER_INVALID"),
        ("retarget-project", "STATE_MARKER_MISMATCH"),
        ("retarget-root", "STATE_MARKER_MISMATCH"),
        ("permissions", "STATE_MARKER_PERMISSIONS_INVALID"),
    ],
)
def test_clean_rejects_invalid_ownership_marker_before_compose_or_rmtree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    code: str,
) -> None:
    runtime = options(tmp_path)
    ensure_state(runtime)
    sentinel = runtime.state_root / "preserve"
    sentinel.write_text("user-data", encoding="utf-8")
    if mutation == "malformed":
        runtime.marker_path.write_text("not-json", encoding="utf-8")
    elif mutation in {"retarget-project", "retarget-root"}:
        payload = json.loads(runtime.marker_path.read_text(encoding="utf-8"))
        if mutation == "retarget-project":
            payload["project"] = "another-project"
        else:
            payload["root"] = str(tmp_path / "another-root")
        runtime.marker_path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        runtime.marker_path.chmod(0o644)

    def forbidden(*_: object, **__: object) -> object:
        raise AssertionError("invalid ownership must be rejected before Compose")

    monkeypatch.setattr("scripts.local_runtime.run_checked", forbidden)

    with pytest.raises(RuntimeFailure, match=code):
        command_clean(runtime, CLEAN_CONFIRMATION)

    assert sentinel.read_text(encoding="utf-8") == "user-data"


def test_clean_rejects_marker_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = options(tmp_path)
    ensure_state(runtime)
    marker_payload = runtime.marker_path.read_text(encoding="utf-8")
    external_marker = tmp_path / "external-marker"
    external_marker.write_text(marker_payload, encoding="utf-8")
    external_marker.chmod(0o600)
    runtime.marker_path.unlink()
    runtime.marker_path.symlink_to(external_marker)
    monkeypatch.setattr(
        "scripts.local_runtime.run_checked",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("marker symlink must be rejected before Compose")
        ),
    )

    with pytest.raises(RuntimeFailure, match="STATE_MARKER_INVALID"):
        command_clean(runtime, CLEAN_CONFIRMATION)

    assert runtime.state_root.exists()


def test_clean_rejects_non_regular_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = options(tmp_path)
    ensure_state(runtime)
    runtime.marker_path.unlink()
    runtime.marker_path.mkdir()
    monkeypatch.setattr(
        "scripts.local_runtime.run_checked",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("non-regular marker must be rejected before Compose")
        ),
    )

    with pytest.raises(RuntimeFailure, match="STATE_MARKER_INVALID"):
        command_clean(runtime, CLEAN_CONFIRMATION)

    assert runtime.state_root.exists()


def test_clean_revalidates_marker_after_compose_before_rmtree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = options(tmp_path)
    ensure_state(runtime)
    sentinel = runtime.state_root / "preserve"
    sentinel.write_text("user-data", encoding="utf-8")

    def retarget_after_compose(*_: object, **__: object) -> SimpleNamespace:
        payload = json.loads(runtime.marker_path.read_text(encoding="utf-8"))
        payload["root"] = str(tmp_path / "another-root")
        runtime.marker_path.write_text(json.dumps(payload), encoding="utf-8")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("scripts.local_runtime.run_checked", retarget_after_compose)

    with pytest.raises(RuntimeFailure, match="STATE_MARKER_MISMATCH"):
        command_clean(runtime, CLEAN_CONFIRMATION)

    assert sentinel.read_text(encoding="utf-8") == "user-data"


def test_clean_rejects_state_root_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = options(tmp_path)
    ensure_state(runtime)
    linked_root = tmp_path / "linked-state"
    linked_root.symlink_to(runtime.state_root, target_is_directory=True)
    linked_runtime = replace(runtime, state_root=linked_root)
    monkeypatch.setattr(
        "scripts.local_runtime.run_checked",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("root symlink must be rejected before Compose")
        ),
    )

    with pytest.raises(RuntimeFailure, match="STATE_ROOT_INVALID"):
        command_clean(linked_runtime, CLEAN_CONFIRMATION)

    assert runtime.state_root.exists()


def test_unavailable_report_lists_every_entry_and_contains_no_input_details() -> None:
    report = unavailable_report("test", ("generation.high_precision",))

    assert report["status"] == "not_ready"
    assert {item["id"] for item in report["components"]} == {
        "control.api",
        "metadata.postgres",
        "artifact.local",
        "worker.default",
    }
    heavy = next(
        item for item in report["capabilities"]
        if item["id"] == "generation.high_precision"
    )
    assert heavy["required"] is True
    assert heavy["provider"] == "deepseek"
    assert heavy["model"] == "deepseek-v4-pro"
    assert "exception" not in json.dumps(report).lower()
