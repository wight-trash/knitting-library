"""Convert a guide from format 0.1 to 0.2. Mechanical: new fields get empty defaults; nothing is invented.

    python migrate_01_to_02.py IN.json [OUT.json]     (OUT defaults to IN, overwritten)

Changes: sized values gain from_picture (from the nearest source) and alt; applies_to gains except; needle kind becomes
kinds and length a sized value; checkpoints become {kind, total, parts, text}; schedules, targets and repeats gain
their new fields; section reminders move to the top-level reminders list (spanning that section's steps); pieces is
empty; doubts gain origin "person" and target null.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def is_sized(node) -> bool:
    return isinstance(node, dict) and {"text", "unit", "all", "by_size", "by_choice"} <= node.keys() and "kind" not in node


def sized(node, pic: bool):
    if node is None:
        return None
    out = {k: node[k] for k in ("text", "unit", "all", "by_size", "by_choice")}
    out["from_picture"] = bool(pic)
    out["alt"] = None
    return out


def walk_sized(node, pic: bool = False):
    """Upgrade every sized value in a subtree, taking from_picture from the closest enclosing source."""
    if isinstance(node, dict):
        src = node.get("source")
        if isinstance(src, dict) and "from_picture" in src:
            pic = src["from_picture"]
        for k, v in list(node.items()):
            if is_sized(v):
                node[k] = sized(v, pic)
            else:
                walk_sized(v, pic)
    elif isinstance(node, list):
        for idx, v in enumerate(node):
            if is_sized(v):
                node[idx] = sized(v, pic)
            else:
                walk_sized(v, pic)


def applies(a):
    if a is None:
        return None
    return {"sizes": a.get("sizes"), "choices": a.get("choices"), "except": a.get("except", [])}


def schedule(sc: dict) -> dict:
    return {"action": sc["action"], "slots": [], "every": sc.get("every"), "every_unit": sc.get("every_unit"),
            "on_rows": None, "times": sc.get("times"), "first_at": sc.get("first_at"), "until": None,
            "checkpoint": None, "source": sc["source"]}


def migrate(g: dict) -> dict:
    if g.get("schema_version") == "0.2":
        return g
    g["schema_version"] = "0.2"
    g.setdefault("build", None)
    for x in g["gauge"]:
        x.setdefault("rows_unit", None)
        x["applies_to"] = None
    for n in g["needles"]:
        n["kinds"] = [n.pop("kind")]
        length = n.get("length")
        n["length"] = None if length is None else {"text": length, "unit": None, "all": length, "by_size": None,
                                                    "by_choice": None}
        n["applies_to"] = None
    for y in g["yarns"]:
        y.setdefault("alternatives_text", None)
        y["applies_to"] = None
    for n in g["notions"]:
        n["amount"] = None
        n["applies_to"] = None
    for t in g["techniques"]:
        t.setdefault("slots", [])
    for c in g["charts"]:
        c["applies_to"] = applies(c["applies_to"])
        sp = c.pop("start_point", None)
        c["width"], c["height"] = None, None
        c["start_points"] = [] if sp is None else [{"section_id": None, "label": None, "value": sp}]
    reminders = []
    for sec in g["sections"]:
        steps = sec["steps"]
        for r_i, r in enumerate(sec.pop("reminders", [])):
            reminders.append({"id": f"{sec['id']}-reminder-{r_i + 1}", "text": r["action"], "schedule": schedule(r),
                              "from_step": steps[0]["id"] if steps else sec["id"],
                              "until_step": steps[-1]["id"] if steps else None, "source": r["source"]})
        for st in steps:
            st["applies_to"] = applies(st["applies_to"])
            t = st["target"]
            t.setdefault("measured_from", None)
            t.setdefault("ending", None)
            t.setdefault("match", None)
            if st.get("repeat"):
                rp = st["repeat"]
                rp.setdefault("until_row", None)
                rp.setdefault("until_text", None)
                rp.setdefault("includes_earlier_text", None)
            cp = st.get("checkpoint")
            st["checkpoint"] = None if cp is None else {"kind": "stitches", "total": cp, "parts": [], "text": None}
            st["schedules"] = [schedule(sc) for sc in st["schedules"]]
            st.setdefault("based_on", None)
            st.setdefault("optional", False)
    g["pieces"] = []
    g["reminders"] = reminders
    for d in g["doubts"]:
        d.setdefault("origin", "person")
        d.setdefault("target", None)
    walk_sized(g)
    order = ["schema_version", "build", "pattern", "options", "size_guide", "gauge", "needles", "yarns", "notions",
             "abbreviations", "techniques", "charts", "sections", "pieces", "reminders", "links", "doubts"]
    return {k: g[k] for k in order}


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src
    out = migrate(json.loads(src.read_text(encoding="utf-8")))
    dst.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("migrated", src, "->", dst)
