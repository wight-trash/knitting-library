"""Check a guide file against guide-schema.json and the format rules the schema cannot express.

    python validate_guide.py GUIDE.json [GUIDE.json ...]

Needs the `jsonschema` package. Exits non-zero if any file has problems. Problems are printed one per line.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "guide-schema.json").read_text(encoding="utf-8"))
SLOT_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")
warnings: list[str] = []  # filled by check(): short size lists that a list_length doubt accounts for


def sized_values(node, path="$"):
    """Yield (path, sized_value) for every sized_value-shaped object in the guide."""
    if isinstance(node, dict):
        if {"text", "unit", "all", "by_size", "by_choice"} <= node.keys():
            yield path, node
        for key, value in node.items():
            yield from sized_values(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from sized_values(value, f"{path}[{i}]")


def check(guide: dict) -> list[str]:
    problems = [f"schema: {'/'.join(map(str, e.path)) or '$'}: {e.message}" for e in Draft202012Validator(SCHEMA).iter_errors(guide)]
    if problems:
        return problems

    warnings.clear()
    has_length_doubt = any(d["kind"] == "list_length" for d in guide["doubts"])
    sizes = [s["id"] for s in guide["options"]["sizes"]]
    choice_values = {v["id"] for c in guide["options"]["choices"] for v in c["values"]}
    if len(sizes) != len(set(sizes)):
        problems.append("options.sizes: duplicate size ids")
    if len(guide["options"]["choices"]) > 2:
        problems.append("options.choices: more than two choices")

    for path, sv in sized_values(guide):
        used = [k for k in ("all", "by_size", "by_choice") if sv[k] is not None]
        if len(used) > 1:
            problems.append(f"{path}: at most one of all/by_size/by_choice, has {used}")
        lists = []
        if sv["by_size"] is not None:
            lists.append(("by_size", sv["by_size"]))
        for entry in sv["by_choice"] or []:
            if entry["choice"] not in choice_values:
                problems.append(f"{path}.by_choice: unknown choice {entry['choice']!r}")
            lists.append((f"by_choice[{entry['choice']}]", entry["by_size"]))
        for name, values in lists:
            if len(values) != len(sizes):
                msg = f"{path}.{name}: {len(values)} values for {len(sizes)} sizes"
                if has_length_doubt:
                    warnings.append(msg)
                else:
                    problems.append(msg + " (if the pattern really is short, record a list_length doubt)")

    def check_applies(where, applies):
        if applies is None:
            return
        for s in applies["sizes"] or []:
            if s not in sizes:
                problems.append(f"{where}.applies_to: unknown size {s!r}")
        for c in applies["choices"] or []:
            if c not in choice_values:
                problems.append(f"{where}.applies_to: unknown choice {c!r}")

    technique_ids = {t["id"] for t in guide["techniques"]}
    chart_ids = {c["id"] for c in guide["charts"]}
    section_id_set = {sec["id"] for sec in guide["sections"]}
    for c in guide["charts"]:
        check_applies(f"chart {c['id']}", c["applies_to"])
        for sp in c.get("start_points", []):
            if sp["section_id"] is not None and sp["section_id"] not in section_id_set:
                problems.append(f"chart {c['id']}: start point for unknown section {sp['section_id']!r}")
    for group in ("gauge", "needles", "yarns", "notions"):
        for idx, item in enumerate(guide.get(group, [])):
            check_applies(f"{group}[{idx}]", item.get("applies_to"))
    for piece in guide.get("pieces", []):
        for sid in piece["section_ids"]:
            if sid not in section_id_set:
                problems.append(f"piece {piece['id']}: unknown section {sid!r}")
        for inst in piece["instances"]:
            if inst["choice"] is not None and inst["choice"] not in choice_values:
                problems.append(f"piece {piece['id']}: unknown choice {inst['choice']!r}")

    step_ids: list[str] = []
    section_ids = [s["id"] for s in guide["sections"]]
    if len(section_ids) != len(set(section_ids)):
        problems.append("sections: duplicate section ids")
    for section in guide["sections"]:
        for step in section["steps"]:
            sid = step["id"]
            step_ids.append(sid)
            where = f"step {sid}"
            check_applies(where, step["applies_to"])
            slot_names = [s["name"] for s in step["slots"]]
            in_text = set(SLOT_RE.findall(step["text"]))
            for name in in_text - set(slot_names):
                problems.append(f"{where}: text uses {{{name}}} but there is no such slot")
            for name in set(slot_names) - in_text:
                problems.append(f"{where}: slot {name!r} is not used in the text")
            for t in step["technique_ids"]:
                if t not in technique_ids:
                    problems.append(f"{where}: unknown technique id {t!r}")
            for c in step["chart_ids"]:
                if c not in chart_ids:
                    problems.append(f"{where}: unknown chart id {c!r}")
            if step["type"] == "repeat" and step["repeat"] is None:
                problems.append(f"{where}: type is repeat but repeat is null")
            if step["type"] == "measure" and step["target"]["kind"] != "length":
                problems.append(f"{where}: type is measure but target.kind is {step['target']['kind']!r}")
    if len(step_ids) != len(set(step_ids)):
        dupes = sorted({s for s in step_ids if step_ids.count(s) > 1})
        problems.append(f"steps: duplicate ids {dupes}")
    for r in guide.get("reminders", []):
        for key in ("from_step", "until_step"):
            if r[key] is not None and r[key] not in step_ids and r[key] not in section_id_set:
                problems.append(f"reminder {r['id']}: {key} {r[key]!r} is not a step")
    for doubt in guide["doubts"]:
        for s in doubt["step_ids"]:
            if s not in step_ids:
                problems.append(f"doubt {doubt['kind']}: unknown step id {s!r}")
    return problems


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
