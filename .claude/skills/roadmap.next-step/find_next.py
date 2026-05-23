#!/usr/bin/env python3
"""Resolve and print the next roadmap step file (path + full contents).

Selection rules (mirror the prefix convention documented in dev_roadmap/plan.md):
  - If exactly one in_progress_step_*.md exists, use it.
  - Multiple in_progress_*.md files is an anomaly -> exit 2.
  - Otherwise pick the pending step with the smallest NN, where pending = no prefix
    or prefix open_ / to_do_.
  - If nothing pending or in progress, print ROADMAP_COMPLETE and exit 0.

Output format on success:
    PATH: /abs/path/to/dev_roadmap/<prefix>step_NN.md

    <full file contents>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PENDING_PREFIXES = ("open_", "to_do_", "")
STEP_RE = re.compile(r"^(done_|in_progress_|open_|to_do_)?step_(\d+)\.md$")


def find_roadmap_dir(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        roadmap = candidate / "dev_roadmap"
        if (roadmap / "plan.md").is_file():
            return roadmap
    print("error: could not locate dev_roadmap/plan.md from script location", file=sys.stderr)
    sys.exit(1)


def classify(name: str) -> tuple[str, int] | None:
    match = STEP_RE.match(name)
    if not match:
        return None
    prefix = match.group(1) or ""
    number = int(match.group(2))
    return prefix, number


def pick_step(roadmap: Path) -> Path | None:
    in_progress: list[Path] = []
    pending: list[tuple[int, Path]] = []
    for entry in roadmap.iterdir():
        if not entry.is_file():
            continue
        classified = classify(entry.name)
        if classified is None:
            continue
        prefix, number = classified
        if prefix == "in_progress_":
            in_progress.append(entry)
        elif prefix in PENDING_PREFIXES:
            pending.append((number, entry))

    if len(in_progress) > 1:
        names = ", ".join(sorted(p.name for p in in_progress))
        print(f"error: multiple in_progress step files found: {names}", file=sys.stderr)
        sys.exit(2)
    if in_progress:
        return in_progress[0]
    if pending:
        pending.sort(key=lambda item: item[0])
        return pending[0][1]
    return None


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    roadmap = find_roadmap_dir(script_dir)
    step = pick_step(roadmap)
    if step is None:
        print("ROADMAP_COMPLETE")
        return
    print(f"PATH: {step}")
    print()
    sys.stdout.write(step.read_text())


if __name__ == "__main__":
    main()
