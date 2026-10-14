"""Generate the guide format schemas (version 0.2).

    python make_schemas.py

Writes three files next to PLAN.md:
  guide-schema.json       the full guide. Built by code, shown and edited in the app. Rich, because code writes it.
  ai-outline-schema.json  what the AI returns for the whole pattern: options, materials, sections. Lean.
  ai-section-schema.json  what the AI returns for one section: its steps, as quotes. Lean.

"AI marks, code copies": the AI schemas carry exact quotes from the pattern, never retyped numbers. Code finds the
per-size values inside those quotes and builds the full guide.

Every object is closed (additionalProperties false) and lists all its properties as required; optional values are
"anyOf [X, null]". That keeps the schemas usable for strict structured outputs where a provider supports them.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]
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

if __name__ == "__main__":
    for name, sch in (("guide-schema.json", guide), ("ai-outline-schema.json", outline), ("ai-section-schema.json", section)):
        (OUT / name).write_text(json.dumps(sch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote", OUT / name)
