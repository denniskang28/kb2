"""Validate the zero-dependency planning harness and source references."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PATHS = (
    "AGENTS.md",
    ".story-pipeline.json",
    ".story-pipeline/policy.json",
    ".codex/agents/requirements-agent.toml",
    ".codex/agents/story-pipeline-agent.toml",
    "docs/prd.md",
    "docs/core-design.md",
    "docs/current-state.md",
    "docs/feature-map.md",
)
STALE_VALUES = (
    '"adapter": "kb-lean-v1"',
    '"id": "ui-managed-policy"',
    '/Users/denniskang/work/.storyctl-worktrees/kb"',
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def definitions(pattern: str, text: str) -> set[str]:
    return set(re.findall(pattern, text, re.MULTILINE))


def main() -> None:
    missing_paths = [path for path in REQUIRED_PATHS if not (ROOT / path).is_file()]
    if missing_paths:
        raise SystemExit(f"missing required Harness files: {missing_paths}")

    for path in (".story-pipeline.json", ".story-pipeline/policy.json"):
        json.loads(read(path))

    prd = read("docs/prd.md")
    core = read("docs/core-design.md")
    feature_map = read("docs/feature-map.md")
    feature_designs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "docs/designs/features").glob("*.md"))
    )
    stories = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "docs/stories").glob("*.md"))
    )
    all_docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "docs").rglob("*.md"))
    )

    owners = {
        "REQ": definitions(r"\| (REQ-\d{3}) \|", prd),
        "DES": definitions(r"^### (DES-\d{3}):", core),
        "FEAT": definitions(r"\| (FEAT-\d{3}) \|", feature_map),
        "FD": definitions(r"^### (FD-\d{3}):", feature_designs),
        "S": definitions(r"^# (S-\d{3}):", stories),
    }
    missing_ids = {
        prefix: sorted(
            set(re.findall(rf"(?<![A-Z0-9]){prefix}-\d{{3}}", all_docs)) - ids
        )
        for prefix, ids in owners.items()
    }
    missing_ids = {prefix: ids for prefix, ids in missing_ids.items() if ids}
    if missing_ids:
        raise SystemExit(f"undefined source references: {missing_ids}")

    configuration = read(".story-pipeline.json") + read(".story-pipeline/policy.json")
    stale = [value for value in STALE_VALUES if value in configuration]
    if stale:
        raise SystemExit(f"stale ../kb Harness configuration: {stale}")

    counts = " ".join(f"{prefix}={len(ids)}" for prefix, ids in owners.items())
    print(f"Harness check passed: {counts}")


if __name__ == "__main__":
    main()
