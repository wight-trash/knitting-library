"""Run the guide-building pipeline on the private test patterns and score the guides against the references.

    python pipeline_trial.py run   --label NAME [--patterns id ...] [--effort low] [--parallel 3]
    python pipeline_trial.py score --label NAME [--baseline testdata-private/trial/scores-baseline-haiku-single-call.json]

Outputs go to testdata-private/trial/pipeline-NAME/: <id>.json (guide), <id>.report.json (usage, timings),
<id>.progress.jsonl (every progress event, to check the page would never look frozen), scores.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "app" / "backend"))
sys.path.insert(0, str(HERE))
from app.guide_builder import ai  # noqa: E402
from app.guide_builder.pipeline import build_guide  # noqa: E402
import model_trial as mt  # noqa: E402
from migrate_01_to_02 import migrate  # noqa: E402

PRIVATE = ROOT / "testdata-private"
KEY_FILE = Path.home() / ".config" / "knitting" / "openrouter.key"


def run(label: str, pids: list[str], effort: str | None, parallel: int, model: str) -> None:
    out = PRIVATE / "trial" / f"pipeline-{label}"
    out.mkdir(parents=True, exist_ok=True)
    key = KEY_FILE.read_text().strip()

    def one(pid: str) -> None:
        client = ai.Client(ai.AIConfig(api_key=key, model=model, reasoning_effort=effort))
        events = (out / f"{pid}.progress.jsonl").open("w")
        try:
            res = build_guide(str(PRIVATE / "patterns" / f"{pid}.pdf"), client,
                              report=lambda e: (events.write(json.dumps(e.as_dict()) + "\n"), events.flush()))
            (out / f"{pid}.json").write_text(json.dumps(res.guide, indent=1, ensure_ascii=False), encoding="utf-8")
            (out / f"{pid}.report.json").write_text(json.dumps(res.report, indent=1), encoding="utf-8")
            r = res.report
            print(f"{pid:28} {r['seconds']:6}s ${r['cost']:.4f} calls={r['calls']} out={r['completion_tokens']} "
                  f"think={r['reasoning_tokens']} problems={len(r['validation_problems'])} errors={len(r['errors'])}", flush=True)
        except Exception as exc:  # record and carry on with the other patterns
            (out / f"{pid}.report.json").write_text(json.dumps({"error": repr(exc)[:500]}), encoding="utf-8")
            print(f"{pid:28} FAILED {exc!r}"[:200], flush=True)
        finally:
            events.close()
            client.close()

    with ThreadPoolExecutor(parallel) as pool:
        list(pool.map(one, pids))


def score(label: str, baseline: str | None) -> None:
    out = PRIVATE / "trial" / f"pipeline-{label}"
    base = {r["pattern"]: r for r in json.loads(Path(baseline).read_text())} if baseline else {}
    rows = []
    for ref_p in sorted((PRIVATE / "reference").glob("*.json")):
        pid = ref_p.stem
        gp, rp = out / f"{pid}.json", out / f"{pid}.report.json"
        if not gp.exists():
            continue
        ref, guide = json.loads(ref_p.read_text()), json.loads(gp.read_text())
        rep = json.loads(rp.read_text()) if rp.exists() else {}
        problems = mt.validate(guide)
        src = "\n".join(mt.page_texts(PRIVATE / "patterns" / f"{pid}.pdf"))
        rec, prec = mt.overlap(mt.values_by_size(ref), mt.values_by_size(guide))
        cp_rec, _ = mt.overlap(mt.checkpoints(ref), mt.checkpoints(guide))
        ev = [json.loads(l) for l in (out / f"{pid}.progress.jsonl").read_text().splitlines() if l.strip()]
        gaps = [round(b["at"] - a["at"], 1) for a, b in zip(ev, ev[1:])]
        rows.append({
            "pattern": pid, "valid": not problems, "problems": len(problems),
            "sizes_ok": [s["label"] for s in guide["options"]["sizes"]] == [s["label"] for s in ref["options"]["sizes"]],
            "value_recall": round(rec, 3), "value_precision": round(prec, 3), "checkpoint_recall": round(cp_rec, 3),
            "invented": mt.invented(guide, src) if len(src.strip()) > 500 else None,
            "steps": sum(len(s["steps"]) for s in guide["sections"]), "ref_steps": sum(len(s["steps"]) for s in ref["sections"]),
            "low_conf": sum(1 for s in guide["sections"] for st in s["steps"] if st["confidence"] == "low"),
            "doubts": len(guide["doubts"]), "ref_doubts": len(ref["doubts"]),
            "seconds": rep.get("seconds"), "cost": rep.get("cost"), "out_tokens": rep.get("completion_tokens"),
            "think_tokens": rep.get("reasoning_tokens"), "longest_silence_s": max(gaps) if gaps else None,
            "base_recall": base.get(pid, {}).get("value_recall"), "base_precision": base.get(pid, {}).get("value_precision"),
            "base_seconds": base.get(pid, {}).get("seconds"), "base_cost": base.get(pid, {}).get("cost"),
        })
    (out / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    cols = list(rows[0]) if rows else []
    print("\t".join(cols))
    for r in rows:
        print("\t".join(str(r.get(c, "")) for c in cols))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "score"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--patterns", nargs="*")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--model", default="anthropic/claude-haiku-5.5")
    ap.add_argument("--baseline", default=str(PRIVATE / "trial" / "scores-baseline-haiku-single-call.json"))
    a = ap.parse_args()
    if a.action == "run":
        pids = a.patterns or sorted(p.stem for p in (PRIVATE / "reference").glob("*.json"))
        run(a.label, pids, None if a.effort == "none" else a.effort, a.parallel, a.model)
    else:
        score(a.label, a.baseline)


if __name__ == "__main__":
    main()
