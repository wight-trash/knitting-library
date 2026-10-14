"""Build a guide from the command line, for testing.

    python -m app.guide_builder.cli PATTERN.pdf OUT.json [--model M] [--key-file F] [--effort low] [--workers 6]

Prints each progress event as it happens, then a summary. The API key is read from --key-file (default
~/.config/knitting/openrouter.key) or the OPENROUTER_API_KEY environment variable, and never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import ai
from .pipeline import build_guide
from .progress import Event


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("out")
    ap.add_argument("--model", default="anthropic/claude-haiku-5.5")
    ap.add_argument("--key-file", default=str(Path.home() / ".config" / "knitting" / "openrouter.key"))
    ap.add_argument("--effort", default="low", help="reasoning effort: low, medium, high, or none")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--report", help="write the build report (usage, timings, problems) here")
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY") or Path(args.key_file).read_text().strip()
    cfg = ai.AIConfig(api_key=key, model=args.model, reasoning_effort=None if args.effort == "none" else args.effort)
    client = ai.Client(cfg)

    def show(e: Event) -> None:
        d = e.as_dict()
        print(f"[{d['percent']:3d}%] {d['title']}: {d['message']}", flush=True)

    try:
        result = build_guide(args.pdf, client, report=show, workers=args.workers)
    finally:
        client.close()
    Path(args.out).write_text(json.dumps(result.guide, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.report:
        Path(args.report).write_text(json.dumps(result.report, indent=1) + "\n", encoding="utf-8")
    r = result.report
    print(f"done in {r['seconds']} s, {r['calls']} calls, {r['prompt_tokens']} in / {r['completion_tokens']} out "
          f"({r['reasoning_tokens']} thinking), ${r['cost']}, modes {r['modes']}, "
          f"{len(r['validation_problems'])} validation problems, {len(r['errors'])} errors", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
