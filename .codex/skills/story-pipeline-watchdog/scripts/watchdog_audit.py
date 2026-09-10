#!/usr/bin/env python3
"""Append-only watchdog audit logging with deduplication and resume limits."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator


DEFAULT_RUNTIME_DIR = Path(".story-pipeline/runtime/watchdog")
AUTO_CONTINUE = "AUTO_CONTINUE"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def isoformat(value: dt.datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "processedKeys": [], "pendingActions": {}, "stories": {}}
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("version") != 1:
        raise ValueError(f"unsupported state version in {path}")
    state.setdefault("processedKeys", [])
    state.setdefault("pendingActions", {})
    state.setdefault("stories", {})
    return state


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="state-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)


@contextlib.contextmanager
def runtime_lock(runtime_dir: Path) -> Iterator[None]:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime_dir, 0o700)
    lock_path = runtime_dir / ".lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def decision_key(args: argparse.Namespace) -> str:
    material = {
        "decision": args.decision,
        "messageId": args.message_id,
        "reasonCode": args.reason_code,
        "storyId": args.story,
        "threadId": args.thread_id,
        "turnId": args.turn_id,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def print_result(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=True, sort_keys=True))


def begin(args: argparse.Namespace) -> int:
    runtime_dir = args.runtime_dir.resolve()
    state_path = runtime_dir / "state.json"
    events_path = runtime_dir / "events.jsonl"
    now = utc_now()
    key = decision_key(args)
    action_id = key[:20]

    with runtime_lock(runtime_dir):
        state = load_state(state_path)
        if key in state["processedKeys"]:
            print_result(
                {
                    "actionId": action_id,
                    "duplicate": True,
                    "shouldDispatch": False,
                }
            )
            return 0

        story_state = state["stories"].setdefault(
            args.story,
            {
                "autoResumeCount": 0,
                "lastDispatchAt": None,
                "reasonResumeCounts": {},
            },
        )

        if args.decision == AUTO_CONTINUE:
            last_dispatch = parse_timestamp(story_state.get("lastDispatchAt"))
            if last_dispatch is not None:
                elapsed = (now - last_dispatch).total_seconds()
                if elapsed < args.cooldown_seconds:
                    print_result(
                        {
                            "actionId": action_id,
                            "deferred": True,
                            "retryAfterSeconds": int(args.cooldown_seconds - elapsed),
                            "shouldDispatch": False,
                        }
                    )
                    return 0

        effective_decision = args.decision
        effective_reason = args.reason_code
        instruction = args.instruction
        if args.decision == AUTO_CONTINUE:
            reason_count = story_state["reasonResumeCounts"].get(args.reason_code, 0)
            if (
                reason_count >= args.max_reason_resumes
                or story_state["autoResumeCount"] >= args.max_story_resumes
            ):
                effective_decision = "WAIT_USER"
                effective_reason = "RETRY_LIMIT_EXCEEDED"
                instruction = None

        event = {
            "actionId": action_id,
            "decision": effective_decision,
            "eventType": "decision",
            "evidenceRef": args.evidence_ref,
            "instruction": instruction,
            "messageId": args.message_id,
            "observedReasonCode": args.reason_code,
            "observedStatus": args.observed_status,
            "phase": args.phase,
            "reasonCode": effective_reason,
            "storyId": args.story,
            "threadId": args.thread_id,
            "timestamp": isoformat(now),
            "turnId": args.turn_id,
        }
        append_event(events_path, event)

        state["processedKeys"].append(key)
        state["processedKeys"] = state["processedKeys"][-500:]
        should_dispatch = effective_decision == AUTO_CONTINUE
        if should_dispatch:
            state["pendingActions"][action_id] = {
                "decisionKey": key,
                "reasonCode": args.reason_code,
                "storyId": args.story,
            }
        write_state(state_path, state)

    print_result(
        {
            "actionId": action_id,
            "decision": effective_decision,
            "duplicate": False,
            "reasonCode": effective_reason,
            "shouldDispatch": should_dispatch,
        }
    )
    return 0


def finish(args: argparse.Namespace) -> int:
    runtime_dir = args.runtime_dir.resolve()
    state_path = runtime_dir / "state.json"
    events_path = runtime_dir / "events.jsonl"
    now = utc_now()

    with runtime_lock(runtime_dir):
        state = load_state(state_path)
        pending = state["pendingActions"].pop(args.action_id, None)
        if pending is None:
            print_result({"actionId": args.action_id, "unknownAction": True})
            return 2

        append_event(
            events_path,
            {
                "actionId": args.action_id,
                "dispatchStatus": args.dispatch_status,
                "eventType": "dispatch",
                "timestamp": isoformat(now),
            },
        )
        if args.dispatch_status == "sent":
            story_state = state["stories"][pending["storyId"]]
            story_state["autoResumeCount"] += 1
            reason = pending["reasonCode"]
            counts = story_state["reasonResumeCounts"]
            counts[reason] = counts.get(reason, 0) + 1
            story_state["lastDispatchAt"] = isoformat(now)
        write_state(state_path, state)

    print_result(
        {
            "actionId": args.action_id,
            "dispatchStatus": args.dispatch_status,
            "recorded": True,
        }
    )
    return 0


def inspect(args: argparse.Namespace) -> int:
    runtime_dir = args.runtime_dir.resolve()
    with runtime_lock(runtime_dir):
        print_result(load_state(runtime_dir / "state.json"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.set_defaults(handler=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    begin_parser = subparsers.add_parser("begin", help="Record a watchdog decision")
    begin_parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    begin_parser.add_argument("--story", required=True)
    begin_parser.add_argument("--thread-id", required=True)
    begin_parser.add_argument("--turn-id", required=True)
    begin_parser.add_argument("--message-id", required=True)
    begin_parser.add_argument("--observed-status", required=True)
    begin_parser.add_argument("--phase", required=True)
    begin_parser.add_argument("--reason-code", required=True)
    begin_parser.add_argument(
        "--decision",
        required=True,
        choices=("AUTO_CONTINUE", "WAIT_USER", "DELIVERED"),
    )
    begin_parser.add_argument("--evidence-ref", required=True)
    begin_parser.add_argument("--instruction")
    begin_parser.add_argument("--cooldown-seconds", type=int, default=240)
    begin_parser.add_argument("--max-reason-resumes", type=int, default=3)
    begin_parser.add_argument("--max-story-resumes", type=int, default=6)
    begin_parser.set_defaults(handler=begin)

    finish_parser = subparsers.add_parser("finish", help="Record dispatch outcome")
    finish_parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    finish_parser.add_argument("--action-id", required=True)
    finish_parser.add_argument("--dispatch-status", choices=("sent", "failed"), required=True)
    finish_parser.set_defaults(handler=finish)

    inspect_parser = subparsers.add_parser("inspect", help="Print current watchdog state")
    inspect_parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    inspect_parser.set_defaults(handler=inspect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "begin" and args.decision == AUTO_CONTINUE and not args.instruction:
        parser.error("AUTO_CONTINUE requires --instruction")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
