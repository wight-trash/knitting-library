"""Check guide files against format 0.2: the schema and the rules a schema cannot express.

    python validate_guide.py GUIDE.json [GUIDE.json ...]

The checks live in the app (app/backend/app/guide_builder/schemas.py). Install `jsonschema` for the schema part.
Exits non-zero if any file has problems.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app" / "backend"))
from app.guide_builder import schemas  # noqa: E402

check = schemas.problems
warnings = schemas.warnings


def main(paths: list[str]) -> int:
    bad = 0
    for p in paths:
        try:
            guide = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{p}: cannot read: {exc}")
            bad += 1
            continue
        problems = check(guide)
        steps = sum(len(s["steps"]) for s in guide.get("sections", [])) if isinstance(guide, dict) else 0
        if problems:
            bad += 1
            print(f"{p}: {len(problems)} problem(s)")
            for line in problems:
                print(f"  {line}")
        else:
            print(f"{p}: ok ({len(guide['sections'])} sections, {steps} steps, {len(guide['doubts'])} doubts)")
        for line in warnings:
            print(f"  warning: {line}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
