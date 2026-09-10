#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = "kb2-lite-dev"
DEFAULT_STATE_ROOT = ROOT / ".runtime" / DEFAULT_PROJECT
DEFAULT_COMPOSE = ROOT / "deploy" / "local" / "compose.yaml"
CAPABILITY_CATALOG = ROOT / "deploy" / "local" / "capabilities.yaml"
CLEAN_CONFIRMATION = "kb2-local-data"
STATE_MARKER_NAME = ".kb2-runtime-owner.json"
STATE_MARKER_VERSION = "kb2-runtime-state/v1"
PROJECT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")
PORT_RELEASE_WAIT_SECONDS = 5.0
PORT_RELEASE_POLL_SECONDS = 0.1


class RuntimeFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RuntimeOptions:
    project: str
    environment: str
    state_root: Path
    compose_files: tuple[Path, ...]
    timeout: int
    api_port: int

    @property
    def secret_path(self) -> Path:
        return self.state_root / "secrets" / "postgres_password"

    @property
    def deepseek_key_path(self) -> Path:
        return self.state_root / "secrets" / "deepseek_api_key"

    @property
    def env_path(self) -> Path:
        return self.state_root / "compose.env"

    @property
    def marker_path(self) -> Path:
        return self.state_root / STATE_MARKER_NAME


def validate_project(project: str) -> str:
    if not PROJECT_PATTERN.fullmatch(project):
        raise RuntimeFailure("PROJECT_NAME_INVALID")
    return project


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            break
        except OSError:
            raise RuntimeFailure("STATE_ROOT_INVALID") from None
        if stat.S_ISLNK(mode):
            raise RuntimeFailure("STATE_ROOT_INVALID")


def validate_state_root(path: Path) -> Path:
    lexical_root = _lexical_absolute(path)
    _reject_symlink_components(lexical_root)
    resolved = lexical_root.resolve()
    forbidden = {Path("/").resolve(), Path.home().resolve(), ROOT.resolve(), ROOT.parent.resolve()}
    if resolved in forbidden or len(resolved.parts) < 4:
        raise RuntimeFailure("STATE_ROOT_UNSAFE")
    return resolved


def _expected_marker(options: RuntimeOptions, canonical_root: Path) -> dict[str, str]:
    validate_project(options.project)
    return {
        "contractVersion": STATE_MARKER_VERSION,
        "project": options.project,
        "root": str(canonical_root),
    }


def _safe_default_root(options: RuntimeOptions, canonical_root: Path) -> bool:
    lexical_root = _lexical_absolute(options.state_root)
    lexical_default = _lexical_absolute(ROOT / ".runtime" / options.project)
    return lexical_root == lexical_default and canonical_root == lexical_default.resolve()


def _write_marker(options: RuntimeOptions, canonical_root: Path) -> None:
    marker = canonical_root / STATE_MARKER_NAME
    temporary = canonical_root / f".{STATE_MARKER_NAME}.{secrets.token_hex(8)}.tmp"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as marker_file:
            json.dump(_expected_marker(options, canonical_root), marker_file, sort_keys=True)
            marker_file.write("\n")
            marker_file.flush()
            os.fsync(marker_file.fileno())
        os.link(temporary, marker, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeFailure("STATE_MARKER_CREATE_FAILED") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _validate_marker(options: RuntimeOptions) -> Path:
    configured_root = _lexical_absolute(options.state_root)
    canonical_root = validate_state_root(configured_root)
    marker = canonical_root / STATE_MARKER_NAME
    try:
        marker_mode = marker.lstat().st_mode
    except OSError:
        raise RuntimeFailure("STATE_MARKER_INVALID") from None
    if not stat.S_ISREG(marker_mode):
        raise RuntimeFailure("STATE_MARKER_INVALID")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(marker, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8") as marker_file:
            marker_stat = os.fstat(marker_file.fileno())
            if not stat.S_ISREG(marker_stat.st_mode):
                raise RuntimeFailure("STATE_MARKER_INVALID")
            if stat.S_IMODE(marker_stat.st_mode) != 0o600:
                raise RuntimeFailure("STATE_MARKER_PERMISSIONS_INVALID")
            payload = json.load(marker_file)
    except RuntimeFailure:
        raise
    except (OSError, ValueError):
        raise RuntimeFailure("STATE_MARKER_INVALID") from None
    if payload != _expected_marker(options, canonical_root):
        raise RuntimeFailure("STATE_MARKER_MISMATCH")
    return canonical_root


def _initialize_or_validate_state(options: RuntimeOptions) -> Path:
    configured_root = _lexical_absolute(options.state_root)
    canonical_root = validate_state_root(configured_root)
    if canonical_root.exists():
        if not canonical_root.is_dir():
            raise RuntimeFailure("STATE_ROOT_INVALID")
        marker = canonical_root / STATE_MARKER_NAME
        if marker.exists() or marker.is_symlink():
            return _validate_marker(options)
        if not _safe_default_root(options, canonical_root) or any(canonical_root.iterdir()):
            raise RuntimeFailure("STATE_ROOT_UNOWNED")
    else:
        canonical_root.mkdir(parents=True, mode=0o700)
    os.chmod(canonical_root, 0o700)
    _write_marker(options, canonical_root)
    return _validate_marker(options)


def ensure_state(options: RuntimeOptions) -> None:
    canonical_root = _initialize_or_validate_state(options)
    secret_dir = canonical_root / "secrets"
    secret_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(options.state_root, 0o700)
    os.chmod(secret_dir, 0o700)
    if options.secret_path.is_symlink():
        raise RuntimeFailure("DATABASE_SECRET_FILE_INVALID")
    if not options.secret_path.exists():
        descriptor = os.open(options.secret_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
            secret_file.write(secrets.token_urlsafe(36))
    if not options.secret_path.is_file():
        raise RuntimeFailure("DATABASE_SECRET_FILE_INVALID")
    os.chmod(options.secret_path, stat.S_IRUSR | stat.S_IWUSR)
    if options.deepseek_key_path.is_symlink():
        raise RuntimeFailure("DEEPSEEK_KEY_FILE_INVALID")
    if not options.deepseek_key_path.exists():
        descriptor = os.open(options.deepseek_key_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    if not options.deepseek_key_path.is_file():
        raise RuntimeFailure("DEEPSEEK_KEY_FILE_INVALID")
    key_mode = stat.S_IMODE(options.deepseek_key_path.stat().st_mode)
    if options.deepseek_key_path.stat().st_size > 0 and key_mode != 0o600:
        raise RuntimeFailure("DEEPSEEK_KEY_FILE_PERMISSIONS_INVALID")
    os.chmod(options.deepseek_key_path, stat.S_IRUSR | stat.S_IWUSR)
    options.env_path.write_text(
        "\n".join(
            (
                f"KB2_PROJECT={options.project}",
                f"KB2_ENVIRONMENT={options.environment}",
                f"KB2_API_PORT={options.api_port}",
                f"KB2_POSTGRES_PASSWORD_FILE={options.secret_path}",
                f"KB2_DEEPSEEK_API_KEY_FILE={options.deepseek_key_path}",
                "KB2_APP_IMAGE=kb2-runtime:0.1.0",
                "",
            )
        ),
        encoding="utf-8",
    )
    os.chmod(options.env_path, stat.S_IRUSR | stat.S_IWUSR)


def compose_command(options: RuntimeOptions, *arguments: str) -> list[str]:
    command = ["docker", "compose", "--project-name", options.project]
    if options.env_path.exists():
        command.extend(("--env-file", str(options.env_path)))
    for compose_file in options.compose_files:
        command.extend(("--file", str(compose_file)))
    command.extend(arguments)
    return command


def run_checked(command: Sequence[str], timeout: int, code: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "COMPOSE_PROGRESS": "plain"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeFailure(code) from exc
    if result.returncode != 0:
        raise RuntimeFailure(code)
    return result


def _port_has_listener(port: int) -> bool:
    try:
        with socket.socket() as sock:
            sock.settimeout(min(PORT_RELEASE_POLL_SECONDS, 0.2))
            return sock.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        # Refused and timed-out localhost connections both mean there is no
        # accepting listener for the Compose-published API endpoint.
        return False


def preflight(options: RuntimeOptions) -> None:
    run_checked(("docker", "compose", "version"), 10, "COMPOSE_UNAVAILABLE")
    running = run_checked(
        compose_command(options, "ps", "--quiet", "api"), 15, "COMPOSE_INSPECTION_FAILED"
    ).stdout.strip()
    if running:
        return
    deadline = time.monotonic() + min(float(options.timeout), PORT_RELEASE_WAIT_SECONDS)
    while True:
        if not _port_has_listener(options.api_port):
            return
        if time.monotonic() >= deadline:
            raise RuntimeFailure("API_PORT_UNAVAILABLE") from None
        time.sleep(PORT_RELEASE_POLL_SECONDS)


def fetch_health(
    options: RuntimeOptions,
    required: tuple[str, ...],
    *,
    capabilities: bool = True,
) -> tuple[int, dict[str, Any]]:
    query = urllib.parse.urlencode([("require", item) for item in required])
    endpoint = "capabilities" if capabilities else "ready"
    url = f"http://127.0.0.1:{options.api_port}/health/{endpoint}"
    if query:
        url = f"{url}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=min(options.timeout, 10)) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            payload = json.load(exc)
        except (ValueError, OSError):
            payload = {"contractVersion": "health/v1", "status": "not_ready"}
        return exc.code, payload
    except (OSError, ValueError):
        return 503, unavailable_report(options.environment, required)


def _catalog_entries() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # The host CLI intentionally has no package dependencies. This small reader
    # extracts only public IDs/default requirements from the repository catalog.
    sections: dict[str, list[dict[str, Any]]] = {"components": [], "capabilities": []}
    current_section: str | None = None
    current: dict[str, Any] | None = None
    try:
        lines = CAPABILITY_CATALOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], []
    for line in lines:
        stripped = line.strip()
        if stripped in {"components:", "capabilities:"}:
            current_section = stripped[:-1]
            current = None
        elif stripped.startswith("- id:") and current_section:
            current = {"id": stripped.split(":", 1)[1].strip()}
            sections[current_section].append(current)
        elif current is not None and stripped.startswith("required:"):
            current["required"] = stripped.split(":", 1)[1].strip() == "true"
        elif current is not None and stripped.startswith("provider:"):
            current["provider"] = stripped.split(":", 1)[1].strip()
        elif current is not None and stripped.startswith("model:"):
            current["model"] = stripped.split(":", 1)[1].strip()
    return sections["components"], sections["capabilities"]


def unavailable_report(environment: str, requested: tuple[str, ...]) -> dict[str, Any]:
    components, capabilities = _catalog_entries()
    requested_set = set(requested)
    return {
        "contractVersion": "health/v1",
        "environment": environment,
        "status": "not_ready",
        "checkedAt": None,
        "components": [
            {
                "id": item["id"],
                "required": item.get("required", False),
                "status": "unavailable",
                "code": "CONTROL_API_UNAVAILABLE",
                "latencyMs": 0,
            }
            for item in components
        ],
        "capabilities": [
            {
                "id": item["id"],
                "required": item.get("required", False) or item["id"] in requested_set,
                "status": "unavailable",
                "code": "CONTROL_API_UNAVAILABLE",
                "latencyMs": 0,
                "provider": item.get("provider"),
                **({"model": item["model"]} if item.get("model") else {}),
            }
            for item in capabilities
        ],
    }


def print_health(report: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
        return
    print(f"environment={report.get('environment', 'unknown')} status={report.get('status', 'not_ready')}")
    for group in ("components", "capabilities"):
        for entry in report.get(group, []):
            provider = f" provider={entry['provider']}" if entry.get("provider") else ""
            model = f" model={entry['model']}" if entry.get("model") else ""
            print(
                f"{group[:-1]}={entry.get('id', 'unknown')} required={str(bool(entry.get('required'))).lower()} "
                f"status={entry.get('status', 'unavailable')} code={entry.get('code', 'INVALID_RESPONSE')}"
                f"{provider}{model}"
            )


def command_up(options: RuntimeOptions) -> int:
    ensure_state(options)
    preflight(options)
    run_checked(
        compose_command(
            options,
            "up",
            "--build",
            "--detach",
            "--wait",
            "--wait-timeout",
            str(options.timeout),
        ),
        options.timeout + 300,
        "LOCAL_START_FAILED",
    )
    deadline = time.monotonic() + options.timeout
    report: dict[str, Any] = unavailable_report(options.environment, ())
    while time.monotonic() < deadline:
        _, report = fetch_health(options, (), capabilities=False)
        if report.get("status") == "ready":
            print_health(report, False)
            return 0
        time.sleep(0.5)
    print_health(report, False)
    return 1


def command_health(options: RuntimeOptions, required: tuple[str, ...], as_json: bool) -> int:
    status, report = fetch_health(options, required)
    print_health(report, as_json)
    return 0 if status == 200 and report.get("status") == "ready" else 1


def command_stop(options: RuntimeOptions) -> int:
    run_checked(
        compose_command(options, "down", "--remove-orphans"),
        options.timeout,
        "LOCAL_STOP_FAILED",
    )
    print(f"project={options.project} status=stopped data=preserved")
    return 0


def command_clean(options: RuntimeOptions, confirmation: str) -> int:
    if confirmation != CLEAN_CONFIRMATION:
        raise RuntimeFailure("CLEAN_CONFIRMATION_REQUIRED")
    canonical_root = _validate_marker(options)
    run_checked(
        compose_command(options, "down", "--volumes", "--remove-orphans"),
        options.timeout,
        "LOCAL_CLEAN_FAILED",
    )
    if _validate_marker(options) != canonical_root:
        raise RuntimeFailure("STATE_MARKER_MISMATCH")
    shutil.rmtree(canonical_root)
    print(f"project={options.project} status=cleaned data=removed")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Scoped Knowledge Engine Lite local runtime")
    result.add_argument("--project", default=DEFAULT_PROJECT)
    result.add_argument("--environment", default="local")
    result.add_argument("--state-root", type=Path)
    result.add_argument("--compose-file", type=Path, default=DEFAULT_COMPOSE)
    result.add_argument("--overlay", action="append", type=Path, default=[])
    result.add_argument("--timeout", type=int, default=180)
    result.add_argument("--api-port", type=int, default=8010)
    subparsers = result.add_subparsers(dest="command", required=True)
    subparsers.add_parser("up")
    health = subparsers.add_parser("health")
    health.add_argument("--require", action="append", default=[])
    health.add_argument("--json", action="store_true")
    subparsers.add_parser("stop")
    clean = subparsers.add_parser("clean")
    clean.add_argument("--confirm", default="")
    return result


def options_from(args: argparse.Namespace) -> RuntimeOptions:
    project = validate_project(args.project)
    state_root = _lexical_absolute(args.state_root or (ROOT / ".runtime" / project))
    validate_state_root(state_root)
    compose_files = (args.compose_file.resolve(), *(path.resolve() for path in args.overlay))
    if not all(path.is_file() for path in compose_files):
        raise RuntimeFailure("COMPOSE_FILE_UNAVAILABLE")
    if args.timeout < 1 or not 1 <= args.api_port <= 65535:
        raise RuntimeFailure("RUNTIME_ARGUMENT_INVALID")
    return RuntimeOptions(
        project=project,
        environment=args.environment,
        state_root=state_root,
        compose_files=compose_files,
        timeout=args.timeout,
        api_port=args.api_port,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        options = options_from(args)
        if args.command == "up":
            return command_up(options)
        if args.command == "health":
            return command_health(options, tuple(args.require), args.json)
        if args.command == "stop":
            return command_stop(options)
        if args.command == "clean":
            return command_clean(options, args.confirm)
        raise RuntimeFailure("COMMAND_INVALID")
    except RuntimeFailure as exc:
        print(f"status=failed code={exc.code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
