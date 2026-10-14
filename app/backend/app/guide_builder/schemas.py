"""The guide format schemas (version 0.2) and the checks a schema cannot express.

Three schemas:
  guide-schema.json       the full guide. Built by code, shown and edited in the app. Rich, because code writes it.
  ai-outline-schema.json  what the AI returns for the whole pattern: options, materials, sections. Lean.
  ai-section-schema.json  what the AI returns for one section: its steps, as quotes. Lean.

"AI marks, code copies": the AI schemas carry exact quotes from the pattern, never retyped numbers. Code finds the
per-size values inside those quotes and builds the full guide.

Every object is closed (additionalProperties false) and lists all its properties as required; optional values are
"anyOf [X, null]". That keeps the schemas usable for strict structured outputs where a provider supports them.
"""
from __future__ import annotations

import re
VERSION = "0.2"


# ---------------------------------------------------------------- helpers
def s(desc: str | None = None, enum: list[str] | None = None) -> dict:
    d: dict = {"type": "string"}
    if enum:
        d["enum"] = enum
    if desc:
        d["description"] = desc
    return d


def i(desc: str | None = None) -> dict:
    return {"type": "integer", **({"description": desc} if desc else {})}


def b(desc: str | None = None) -> dict:
    return {"type": "boolean", **({"description": desc} if desc else {})}


def arr(item: dict, desc: str | None = None) -> dict:
    return {"type": "array", "items": item, **({"description": desc} if desc else {})}


def obj(props: dict, desc: str | None = None) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props,
            **({"description": desc} if desc else {})}


def opt(x: dict, desc: str | None = None) -> dict:
    d = {"anyOf": [x, {"type": "null"}]}
    if desc:
        d["description"] = desc
    return d


def ref(name: str) -> dict:
    return {"$ref": f"#/$defs/{name}"}


def schema(title: str, desc: str, root: dict, defs: dict) -> dict:
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"guided-knitting/{title}/{VERSION}",
            "title": title, "description": desc, **root, "$defs": defs}


UNITS = ["stitches", "rows", "rounds", "row_pairs", "repeats", "times", "cm", "mm", "in", "m", "yd", "g", "oz",
         "balls", "skeins", "pieces", "other"]
DOUBT_KINDS = ["list_length", "arithmetic", "conflict", "missing", "from_picture", "ambiguous", "outside_pattern",
               "unreadable", "other"]
STEP_TYPES = ["instruction", "rows", "repeat", "measure", "pick_up", "tick", "chart"]
TARGET_KINDS = ["rows", "rounds", "repeats", "length", "row_number", "match", "none"]

# ---------------------------------------------------------------- full guide
G: dict = {}
G["source"] = obj({
    "page": opt(i("1-based PDF page")),
    "quote": s("Word for word from the pattern, short"),
    "from_picture": b("Read from an image rather than the text layer"),
}, "Where in the pattern this came from.")
G["unit"] = opt(s(enum=UNITS))
G["per_size"] = arr(opt(s()), "One entry per size, in options.sizes order: the value as written, \"-\" when it does "
                              "not apply to that size, null when the pattern gives none.")
G["by_choice"] = arr(obj({"choice": s("An id from options.choices[].values[].id"), "by_size": ref("per_size")}))
_core = {
    "text": s("The original text, e.g. \"92-96-100 sts\" or \"13 (15, 17)\""),
    "unit": ref("unit"),
    "all": opt(s(), "The same value for every size"),
    "by_size": opt(ref("per_size")),
    "by_choice": opt(ref("by_choice"), "When the value also depends on an extra choice such as yarn weight"),
}
G["sized_alt"] = obj(dict(_core), "The same value in another unit, as the pattern also gives it (e.g. inches beside cm).")
G["sized_value"] = obj({**_core, "from_picture": b(), "alt": opt(ref("sized_alt"))},
                       "A value that may differ by size and choice. At most one of all/by_size/by_choice; none of them "
                       "means the pattern gives no value. Values are copied, never converted or calculated.")
G["applies_to"] = opt(obj({
    "sizes": opt(arr(s()), "Size ids; null means all sizes"),
    "choices": opt(arr(s()), "Choice value ids; null means all"),
    "except": arr(obj({"size": opt(s()), "choice": opt(s())}), "Combinations excluded, e.g. fingering M"),
}), "Which sizes and choices this applies to. null means all.")
G["pattern"] = obj({
    "title": s(), "designer": opt(s()), "publisher": opt(s()), "pattern_number": opt(s()),
    "language": s(), "translated_from": opt(s()),
    "units_in_source": s(enum=["cm", "in", "cm_first", "in_first"]),
    "garment": opt(s()), "construction": opt(s()),
    "made_to_measure": b("Stitch counts are placeholders the knitter works out"),
    "summary": opt(s()),
})
G["options"] = obj({
    "sizes": arr(obj({"id": s(), "label": s()})),
    "size_notation": s("How per-size values are written, e.g. \"dash list\", \"a (b, c)\", \"a (b) c (d)\""),
    "choices": arr(obj({"id": s(), "name": s(), "values": arr(obj({"id": s(), "label": s()}))}),
                   "At most two choices besides size"),
})
G["size_guide"] = obj({
    "kind": s(enum=["table", "image", "both", "list", "none"]),
    "page": opt(i()),
    "measurements": arr(obj({"name": s(), "value": ref("sized_value"), "source": ref("source")})),
})
G["gauge"] = obj({
    "text": s(), "stitches": opt(s()), "rows": opt(s()),
    "rows_unit": opt(s(enum=["rows", "rounds", "round_pairs"])),
    "over": opt(s("As written, e.g. \"10 cm\", \"4 in\"")), "stitch_pattern": opt(s()),
    "condition": opt(s("e.g. \"after felting\"")), "applies_to": ref("applies_to"), "source": ref("source"),
})
G["needle"] = obj({
    "id": s(), "text": s(), "size_mm": opt(s()), "size_us": opt(s()), "size_uk": opt(s()),
    "kinds": arr(s(enum=["circular", "straight", "double_pointed", "crochet_hook", "other"])),
    "length": opt(ref("sized_value")), "use": opt(s()), "applies_to": ref("applies_to"), "source": ref("source"),
})
G["yarn"] = obj({
    "id": s(), "name": s(), "weight": opt(s()), "fibre": opt(s()), "ball": opt(s()), "colour": opt(s()),
    "strand_group": opt(s("Yarns sharing a strand_group are held together")),
    "alternative_group": opt(s("Different alternative_group values are alternatives (\"or use\")")),
    "alternatives_text": opt(s("Alternatives given without a named yarn, e.g. \"yarn group A + A or C\"")),
    "amount": ref("sized_value"), "applies_to": ref("applies_to"), "source": ref("source"),
})
G["notion"] = obj({"text": s(), "amount": opt(ref("sized_value")), "applies_to": ref("applies_to"),
                   "source": ref("source")})
G["abbreviation"] = obj({"abbr": s(), "meaning": s(), "defined_in_pattern": b(), "source": ref("source")})
G["slot"] = obj({"name": s("Used as {name} in the text"), "value": ref("sized_value")})
G["technique"] = obj({"id": s(), "name": s(), "text": s(), "slots": arr(ref("slot")), "source": ref("source")})
G["chart"] = obj({
    "id": s(), "name": s(), "page": opt(i()), "kind": s(enum=["image", "vector", "text"]),
    "applies_to": ref("applies_to"),
    "width": opt(ref("sized_value")), "height": opt(ref("sized_value")),
    "start_points": arr(obj({"section_id": opt(s()), "label": opt(s()), "value": ref("sized_value")}),
                        "Where to start, per section or piece where it differs"),
    "written_alternative": b(), "notes": opt(s()), "source": ref("source"),
})
G["checkpoint"] = obj({
    "kind": s(enum=["stitches", "rows_worked", "other"]),
    "total": opt(ref("sized_value")),
    "parts": arr(obj({"label": s(), "value": ref("sized_value")}), "e.g. sleeve, front, sleeve, back"),
    "text": opt(s()),
})
G["schedule"] = obj({
    "action": s("What to do, e.g. \"decrease 1 st each side\""),
    "slots": arr(ref("slot")),
    "every": opt(ref("sized_value")),
    "every_unit": opt(s(enum=["rows", "rounds", "cm", "in", "other"])),
    "on_rows": opt(ref("sized_value"), "An explicit list of rows, e.g. \"rows 32, 40, 48\""),
    "times": opt(ref("sized_value")),
    "first_at": opt(ref("sized_value")),
    "until": opt(obj({"text": s(), "stitches": opt(ref("sized_value"))}), "e.g. \"to 62 sts\""),
    "checkpoint": opt(ref("checkpoint")),
    "source": ref("source"),
}, "Something done repeatedly while working, e.g. AT THE SAME TIME decreases or buttonholes.")
G["target"] = obj({
    "kind": s(enum=TARGET_KINDS),
    "count": opt(ref("sized_value")), "length": opt(ref("sized_value")), "until_row": opt(ref("sized_value")),
    "measured_from": opt(s("e.g. \"from the cast-on edge\"")),
    "ending": opt(s("e.g. \"ending with a WS row\"")),
    "match": opt(obj({"text": s(), "step_id": opt(s())}), "e.g. \"until the same row as the back\""),
})
G["repeat"] = obj({
    "rows_in_repeat": opt(ref("sized_value")), "times": opt(ref("sized_value")), "until_row": opt(ref("sized_value")),
    "until_text": opt(s()),
    "includes_first": opt(b(), "Whether the count includes the first time; null when ambiguous"),
    "includes_earlier_text": opt(s("When a total counts rows from earlier steps too")),
})
G["based_on"] = obj({"section_id": s(), "from_text": opt(s()), "to_text": opt(s()), "changes": opt(s())},
                    "\"Work as for the front from ** to **, but ...\"")
G["step"] = obj({
    "id": s("Stable, e.g. \"yoke-3\""), "type": s(enum=STEP_TYPES),
    "text": s("The instruction as written, with per-size values replaced by {slot} names"),
    "slots": arr(ref("slot")), "applies_to": ref("applies_to"),
    "target": ref("target"), "repeat": opt(ref("repeat")), "checkpoint": opt(ref("checkpoint")),
    "schedules": arr(ref("schedule")), "technique_ids": arr(s()), "chart_ids": arr(s()),
    "based_on": opt(ref("based_on")), "optional": b(),
    "source": ref("source"), "confidence": s(enum=["high", "medium", "low"]),
})
G["section"] = obj({
    "id": s(), "name": s(), "instances": arr(s(), "Labels when worked more than once"), "mirrored": b(),
    "implied": b("The repeat is not stated in the pattern"), "steps": arr(ref("step")), "source": ref("source"),
})
G["piece"] = obj({
    "id": s(), "name": s(), "section_ids": arr(s()),
    "instances": arr(obj({"label": s(), "choice": opt(s())}), "e.g. 1st slipper = left foot"),
    "mirrored": b(), "implied": b(),
}, "A piece made of several sections and worked more than once, e.g. two slippers.")
G["reminder"] = obj({
    "id": s(), "text": s(), "schedule": opt(ref("schedule")),
    "from_step": s(), "until_step": opt(s(), "null: until the end"), "source": ref("source"),
}, "A running instruction across steps or sections, e.g. I-cord edge, buttonholes every 8 cm.")
G["link"] = obj({"label": s(), "url": s(), "page": opt(i()), "outside_pattern": b()})
G["doubt"] = obj({
    "kind": s(enum=DOUBT_KINDS), "message": s("Plain English, for the knitter"),
    "origin": s(enum=["ai", "code", "person"]),
    "step_ids": arr(s()),
    "target": opt(obj({"path": opt(s("e.g. yarns[2].amount")), "sizes": opt(arr(s())), "choices": opt(arr(s()))})),
    "source": opt(ref("source")),
})
G["build"] = obj({"pipeline": s(), "model": opt(s()), "created": s()})

guide = schema(
    "guide-schema",
    "A knitting pattern as a guided structure, built by code from the AI's marks and the pattern text. Values are "
    "copied as written; conversion and arithmetic happen when the guide is shown.",
    {"type": "object", "additionalProperties": False,
     "required": ["schema_version", "build", "pattern", "options", "size_guide", "gauge", "needles", "yarns",
                  "notions", "abbreviations", "techniques", "charts", "sections", "pieces", "reminders", "links",
                  "doubts"],
     "properties": {
         "schema_version": s(enum=[VERSION]), "build": opt(ref("build")),
         "pattern": ref("pattern"), "options": ref("options"), "size_guide": ref("size_guide"),
         "gauge": arr(ref("gauge")), "needles": arr(ref("needle")), "yarns": arr(ref("yarn")),
         "notions": arr(ref("notion")), "abbreviations": arr(ref("abbreviation")),
         "techniques": arr(ref("technique")), "charts": arr(ref("chart")), "sections": arr(ref("section")),
         "pieces": arr(ref("piece")), "reminders": arr(ref("reminder")), "links": arr(ref("link")),
         "doubts": arr(ref("doubt")),
     }},
    G,
)

# ---------------------------------------------------------------- AI: outline
QUOTE = "Copy word for word from the pattern"
O: dict = {}
O["doubt"] = obj({"kind": s(enum=[k for k in DOUBT_KINDS if k != "arithmetic"]),
                  "message": s("Plain English for the knitter. Never claim arithmetic errors: code checks those."),
                  "page": opt(i())})
outline = schema(
    "ai-outline-schema",
    "Step 1 of building a guide: the pattern's options, materials and sections. Numbers stay inside exact quotes.",
    {"type": "object", "additionalProperties": False,
     "required": ["title", "designer", "publisher", "pattern_number", "language", "translated_from", "garment",
                  "construction", "units_in_source", "made_to_measure", "sizes", "size_notation", "choices",
                  "size_guide", "yarns", "needles", "notions", "gauge", "abbreviations", "techniques", "charts",
                  "sections", "links_outside", "doubts"],
     "properties": {
         "title": s(), "designer": opt(s()), "publisher": opt(s()), "pattern_number": opt(s()),
         "language": s(), "translated_from": opt(s()), "garment": opt(s()), "construction": opt(s()),
         "units_in_source": s(enum=["cm", "in", "cm_first", "in_first"]), "made_to_measure": b(),
         "sizes": arr(s(), "Size labels in the pattern's order; one entry for a one-size pattern"),
         "size_notation": s(),
         "choices": arr(obj({"name": s(), "values": arr(s())}), "At most two choices besides size"),
         "size_guide": obj({"kind": s(enum=["table", "image", "both", "list", "none"]), "page": opt(i()),
                            "rows": arr(obj({"name": s(), "quote": s(QUOTE), "page": opt(i()),
                                             "from_picture": b()}))}),
         "yarns": arr(obj({"name": s(), "weight": opt(s()), "fibre": opt(s()), "ball": opt(s()), "colour": opt(s()),
                           "strand_group": opt(s()), "alternative_group": opt(s()), "alternatives_text": opt(s()),
                           "amount_quote": opt(s(QUOTE + ": the per-size amounts")), "page": opt(i()),
                           "from_picture": b(), "choice_value": opt(s("When the yarn belongs to one choice value"))})),
         "needles": arr(obj({"text": s(QUOTE), "page": opt(i()), "choice_value": opt(s())})),
         "notions": arr(obj({"text": s(QUOTE), "page": opt(i())})),
         "gauge": arr(obj({"text": s(QUOTE), "page": opt(i()), "condition": opt(s()), "choice_value": opt(s())})),
         "abbreviations": arr(obj({"abbr": s(), "meaning": s(), "defined": b()})),
         "techniques": arr(obj({"name": s(), "page": opt(i()), "quote": s(QUOTE + ": the whole explanation")})),
         "charts": arr(obj({"name": s(), "page": opt(i()), "kind": s(enum=["image", "vector", "text"]),
                            "applies_text": opt(s("e.g. \"sizes S-XL\"")), "written_alternative": b()})),
         "sections": arr(obj({
             "name": s(), "first_page": opt(i()), "last_page": opt(i()),
             "start_quote": s(QUOTE + ": the first words of the section"),
             "instances": arr(s(), "e.g. [\"1st sleeve\", \"2nd sleeve\"]; empty when worked once"),
             "mirrored": b(), "implied": b(), "based_on_section": opt(s()),
         }), "Construction sections in working order. Front matter is not a section."),
         "links_outside": arr(obj({"label": s(), "url": s(), "page": opt(i())})),
         "doubts": arr(ref("doubt")),
     }},
    O,
)

# ---------------------------------------------------------------- AI: one section
A: dict = {}
A["schedule"] = obj({"action": s(), "every_quote": opt(s(QUOTE)), "every_unit": opt(s(enum=["rows", "rounds", "cm", "in", "other"])),
                     "times_quote": opt(s(QUOTE)), "on_rows_quote": opt(s(QUOTE)), "until_quote": opt(s(QUOTE)),
                     "quote": s(QUOTE + ": the whole instruction")})
A["step"] = obj({
    "type": s(enum=STEP_TYPES),
    "quote": s(QUOTE + ": the whole instruction for this step, exactly as written, including every number"),
    "page": opt(i()),
    "target_kind": s(enum=TARGET_KINDS),
    "count_quote": opt(s(QUOTE + ": the words giving the number of rows/rounds/repeats")),
    "length_quote": opt(s(QUOTE + ": the words giving the length")),
    "until_row_quote": opt(s(QUOTE)),
    "measured_from": opt(s()), "ending": opt(s()),
    "repeat": opt(obj({"rows_quote": opt(s(QUOTE)), "times_quote": opt(s(QUOTE)), "until_quote": opt(s(QUOTE)),
                       "includes_first": opt(b())})),
    "checkpoint_quote": opt(s(QUOTE + ": a stitch count stated after the step")),
    "schedules": arr(ref("schedule"), "AT THE SAME TIME instructions"),
    "techniques": arr(s(), "Names of techniques the step refers to"),
    "charts": arr(s(), "Names of charts the step uses"),
    "sizes_note": opt(s("When the step applies only to some sizes or choices, e.g. \"sizes XL-XXXL only\"")),
    "optional": b(),
    "from_picture": b(),
})
A["doubt"] = O["doubt"]
section = schema(
    "ai-section-schema",
    "Step 2 of building a guide: the steps of one section, as exact quotes. Code finds the numbers in the quotes.",
    {"type": "object", "additionalProperties": False, "required": ["steps", "reminders", "doubts"],
     "properties": {
         "steps": arr(ref("step"), "In working order, one per distinct thing the knitter does or counts"),
         "reminders": arr(obj({"text": s(), "quote": s(QUOTE), "until": opt(s())}),
                          "Running instructions that continue beyond one step"),
         "doubts": arr(ref("doubt")),
     }},
    A,
)


GUIDE, AI_OUTLINE, AI_SECTION = guide, outline, section
SLOT_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")
warnings: list[str] = []  # filled by problems(): short size lists that a list_length doubt accounts for


def _schema_problems(guide_doc: dict) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:  # the app does not need jsonschema: guides are built by code; the rule checks below still run
        return []
    return [f"schema: {'/'.join(map(str, e.path)) or '$'}: {e.message}" for e in Draft202012Validator(GUIDE).iter_errors(guide_doc)]


def sized_values(node, path="$"):
    """Yield (path, sized_value) for every sized_value-shaped object."""
    if isinstance(node, dict):
        if {"text", "unit", "all", "by_size", "by_choice"} <= node.keys():
            yield path, node
        for key, value in node.items():
            yield from sized_values(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i_, value in enumerate(node):
            yield from sized_values(value, f"{path}[{i_}]")


def problems(guide: dict) -> list[str]:
    """Everything wrong with a guide: schema errors (when jsonschema is installed) and the format rules."""
    problems = _schema_problems(guide)
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

