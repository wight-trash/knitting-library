"""Reading a ball band from one photo. Saves nothing: the knitter checks the filled form and taps Save.

The model copies what the band says, as written, with a confidence for each field. Code (guide_builder/units.py)
does every conversion: yards to metres, ounces to grams, US and UK needle sizes to mm, gauge per 4 in to per 10 cm.
Care symbols are not read in this first version.
"""
from __future__ import annotations

import io
import logging
import re

from app.core.foundation import MAX_IMAGE_BYTES
from app.guide_builder import ai, units
from app.guided import settings as guided_settings
from app.stash.ledger import StashError

log = logging.getLogger("knitting.fork.stash")
MAX_SIDE = 1600   # pixels; a phone photo is scaled down before it is sent
CONFIDENCE = ("high", "medium", "low")
TEXT_FIELDS = ("name", "brand", "colour_name", "colour_number", "dye_lot", "fibre", "weight", "care")

SYSTEM = """You read the paper band (label) of a ball or skein of knitting yarn from one photo.
Copy what is printed, exactly as written, in the band's own words and units. Do not convert units, translate,
guess or fill in from your own knowledge of the brand. If a field is not printed or cannot be read, give null.
If the band repeats a value in several languages, use the English one, or the first one.

Fields:
- name: the yarn's name (for example "Merino Soft"), without the brand.
- brand: the maker.
- colour_name and colour_number: the shade name and the shade or colour number.
- dye_lot: the dye lot (often "lot" or "bain").
- fibre: the fibre content as written, with percentages ("80% wool, 20% nylon").
- weight: the yarn weight as written ("DK", "Aran", "4-ply", "Fingering", "DROPS group B"); weight_symbol: the number
  inside the Craft Yarn Council skein symbol (0 to 7) if the band shows one, else null.
- ball_weight: the weight of one ball. text as printed ("50 g / 1.75 oz"); value and unit for ONE of the printed
  values (prefer grams when both are printed); unit is "g", "oz" or "kg".
- length: the length of one ball. text as printed ("125 m / 137 yds"); value and unit for ONE printed value (prefer
  metres); unit is "m" or "yd".
- needle: the recommended needle size, text as printed ("4 mm", "3.5-4 mm", "US 6", "UK 8").
- gauge: the tension. text as printed; stitches and rows as numbers; over_value and over_unit for the square they are
  measured over (10 and "cm", or 4 and "in").
- care: washing and care instructions written in words (ignore the care symbols).

For every field give confidence: "high" when the print is clear, "medium" when partly unclear, "low" when you are
unsure or had to guess between readings."""


def _conf() -> dict:
    return {"type": "string", "enum": list(CONFIDENCE)}


def _nullable(kind: str) -> dict:
    return {"type": [kind, "null"]}


def _obj(props: dict) -> dict:
    props = {**props, "confidence": _conf()}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


SCHEMA: dict = {
    "type": "object",
    "properties": {
        **{f: _obj({"text": _nullable("string")}) for f in TEXT_FIELDS},
        "weight_symbol": _obj({"value": _nullable("integer")}),
        "ball_weight": _obj({"text": _nullable("string"), "value": _nullable("number"), "unit": _nullable("string")}),
        "length": _obj({"text": _nullable("string"), "value": _nullable("number"), "unit": _nullable("string")}),
        "needle": _obj({"text": _nullable("string")}),
        "gauge": _obj({"text": _nullable("string"), "stitches": _nullable("number"), "rows": _nullable("number"),
                       "over_value": _nullable("number"), "over_unit": _nullable("string")}),
    },
    "additionalProperties": False,
}
SCHEMA["required"] = list(SCHEMA["properties"])


# ---------------------------------------------------------------- the photo
_MAGIC = ((b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG", "image/png"))


def _kind(data: bytes) -> str | None:
    for sig, mime in _MAGIC:
        if data.startswith(sig):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"avif"):
        return "image/heic"
    return None


def prepare_photo(data: bytes) -> bytes:
    """A JPEG of at most MAX_SIDE pixels, the right way up. Raises StashError with a plain message."""
    if not data:
        raise StashError("No photo was received. Take the photo again.")
    if len(data) > MAX_IMAGE_BYTES:
        raise StashError("That photo is too big. Use a photo under 20 MB.", 413)
    kind = _kind(data)
    if kind is None:
        raise StashError("That file is not a photo. Use a JPEG, PNG or WebP picture.", 415)
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            img.save(out, "JPEG", quality=85)
            return out.getvalue()
    except Exception:
        if kind == "image/heic":
            raise StashError("This photo format cannot be read here. Set the camera to 'Most Compatible', or "
                             "choose a JPEG picture.", 415) from None
        raise StashError("That photo could not be read. Take it again, or choose another picture.", 415) from None


# ---------------------------------------------------------------- conversions
_WEIGHT_NAMES = [  # Craft Yarn Council categories for plain weight names; longer names first
    (r"super\s*(?:bulky|chunky)|roving", 6), (r"jumbo", 7), (r"lace|cobweb|thread", 0),
    (r"fingering|sock|4[\s-]?ply|super\s*fine|baby", 1), (r"sport|5[\s-]?ply", 2),
    (r"light\s*worsted|\bdk\b|double\s*knit|8[\s-]?ply", 3), (r"worsted|aran|afghan|10[\s-]?ply", 4),
    (r"chunky|bulky|12[\s-]?ply|craft|rug", 5),
]
_NUM = r"\d+(?:[.,]\d+)?(?:\s?[½¼¾])?"
_MM_RANGE = re.compile(rf"({_NUM})\s*(?:mm)?\s*(?:[-–—/]|to)\s*({_NUM})\s*mm", re.IGNORECASE)
_US_RANGE = re.compile(rf"\bUS\s*(?:size\s*)?#?\s*({_NUM})\s*(?:[-–—/]|to)\s*#?\s*({_NUM})", re.IGNORECASE)
_UK_RANGE = re.compile(r"\b(?:UK|Canadian|CA)\s*(?:size\s*)?#?\s*(0{1,3}|\d+)\s*(?:[-–—/]|to)\s*#?\s*(0{1,3}|\d+)\b",
                       re.IGNORECASE)


def weight_category(weight_text: str | None, symbol: int | None) -> int | None:
    if isinstance(symbol, int) and 0 <= symbol <= 7:
        return symbol
    text = (weight_text or "").lower()
    if not text or "drops" in text or "group" in text:
        return None  # DROPS groups span two Craft Yarn Council categories
    for pattern, category in _WEIGHT_NAMES:
        if re.search(pattern, text):
            return category
    return None


def needle_range(text: str | None) -> tuple[float | None, float | None]:
    """(min, max) in mm from "3.5-4 mm", "US 6-7", "UK 8", "4 mm" and so on."""
    if not text:
        return None, None
    m = _MM_RANGE.search(text)
    if m:
        a, b = units.parse_number(m.group(1)), units.parse_number(m.group(2))
        if a is not None and b is not None:
            return min(a, b), max(a, b)
    if not re.search(r"\d\s*mm", text, re.IGNORECASE):
        for rx, prefix in ((_US_RANGE, "US "), (_UK_RANGE, "UK ")):
            m = rx.search(text)
            if m:
                a, b = units.needle_mm(prefix + m.group(1)), units.needle_mm(prefix + m.group(2))
                if a is not None and b is not None:
                    return min(a, b), max(a, b)
    one = units.needle_mm(text)
    return one, one


def _r(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _num(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    parsed = units.parse_number(str(value))
    return parsed if parsed and parsed > 0 else None


def interpret(raw: dict) -> dict:
    """Turn the model's answer into proposed fields, a spec ready for PUT .../spec, and the upstream Add yarn form."""
    def field(name: str) -> dict:
        value = raw.get(name)
        return value if isinstance(value, dict) else {}

    def conf(name: str) -> str:
        c = field(name).get("confidence")
        return c if c in CONFIDENCE else "low"

    def text(name: str) -> str | None:
        t = field(name).get("text")
        t = str(t).strip() if t is not None else ""
        return t or None

    fields: dict = {f: {"text": text(f), "confidence": conf(f)} for f in TEXT_FIELDS}

    bw = field("ball_weight")
    bw_value, bw_unit = _num(bw.get("value")), (bw.get("unit") or "").strip() or None
    grams = units.to_grams(bw_value, bw_unit or "g") if bw_value else None
    fields["grams_per_ball"] = {"text": text("ball_weight"), "original_value": bw_value, "original_unit": bw_unit,
                                "value": _r(grams), "confidence": conf("ball_weight")}

    ln = field("length")
    ln_value, ln_unit = _num(ln.get("value")), (ln.get("unit") or "").strip() or None
    metres = units.to_metres(ln_value, ln_unit or "m") if ln_value else None
    fields["metres_per_ball"] = {"text": text("length"), "original_value": ln_value, "original_unit": ln_unit,
                                 "value": _r(metres), "confidence": conf("length")}

    lo, hi = needle_range(text("needle"))
    fields["needle"] = {"text": text("needle"), "mm_min": lo, "mm_max": hi, "confidence": conf("needle")}

    g = field("gauge")
    sts, rows = _num(g.get("stitches")), _num(g.get("rows"))
    over_value, over_unit = _num(g.get("over_value")), (g.get("over_unit") or "").strip() or None
    sts10 = rows10 = None
    if over_value and over_unit and units.to_cm(over_value, over_unit):
        sts10 = units.gauge_per_10cm(sts, over_value, over_unit) if sts else None
        rows10 = units.gauge_per_10cm(rows, over_value, over_unit) if rows else None
    fields["gauge"] = {"text": text("gauge"), "stitches": sts, "rows": rows, "over_value": over_value,
                       "over_unit": over_unit, "stitches_per_10cm": sts10, "rows_per_10cm": rows10,
                       "confidence": conf("gauge")}

    symbol = field("weight_symbol").get("value")
    symbol = symbol if isinstance(symbol, int) and not isinstance(symbol, bool) else None
    fields["weight_category"] = {"value": weight_category(text("weight"), symbol), "symbol": symbol,
                                 "confidence": conf("weight_symbol") if symbol is not None else conf("weight")}

    spec = {
        "grams_per_ball": fields["grams_per_ball"]["value"], "metres_per_ball": fields["metres_per_ball"]["value"],
        "weight": text("weight"), "weight_category": fields["weight_category"]["value"], "fibre": text("fibre"),
        "needle_mm_min": lo, "needle_mm_max": hi,
        "gauge_stitches": sts10, "gauge_rows": rows10, "gauge_over_cm": 10.0 if (sts10 or rows10) else None,
        "care": text("care"), "source": "ball_band",
    }

    brand, name = text("brand"), text("name")
    full_name = name
    if brand and name and brand.lower() not in name.lower():
        full_name = f"{brand} {name}"
    elif brand and not name:
        full_name = brand
    colour = " ".join(x for x in (text("colour_name"), text("colour_number")) if x) or None
    yardage = None
    if metres and grams:
        yardage = f"{metres:.0f} m per {grams:g} g"
    elif metres:
        yardage = f"{metres:.0f} m"
    needles = None
    if lo and hi:
        needles = f"{lo:g} mm" if lo == hi else f"{lo:g}-{hi:g} mm"
    tension = None
    if sts10:
        tension = f"{sts10:g} sts" + (f" x {rows10:g} rows" if rows10 else "") + " = 10 cm"
    yarn_form = {"name": full_name, "colour": colour, "wool_type": text("fibre"), "yardage": yardage,
                 "needles": needles, "tension": tension}

    low = [k for k, v in fields.items() if v.get("confidence") == "low" and any(
        v.get(x) not in (None, "") for x in ("text", "value", "symbol"))]
    return {"fields": fields, "spec": spec, "yarn_form": yarn_form, "low_confidence": low}


# ---------------------------------------------------------------- the model call
def available() -> bool:
    cfg = guided_settings.ai_connection()
    return bool(cfg["base_url"] and cfg["api_key"])


def read_ball_band(data: bytes) -> dict:
    cfg = guided_settings.ai_connection()
    if not (cfg["base_url"] and cfg["api_key"]):
        raise StashError("The AI connection is not set up yet. An admin can add it in Settings, AI.")
    jpeg = prepare_photo(data)
    client = ai.Client(ai.AIConfig(api_key=cfg["api_key"], base_url=cfg["base_url"] or ai.DEFAULT_BASE_URL,
                                   model=cfg["model"], max_tokens=4000, timeout=90.0, retries=1))
    try:
        answer = client.json(SYSTEM, [ai.text_part("Read this ball band."), ai.image_part(jpeg)], SCHEMA, "ball_band")
    except ai.AIError as exc:
        log.warning("ball band reading failed: %s", exc)
        raise StashError("The ball band could not be read this time. Try again, or fill in the form yourself.",
                         502) from None
    finally:
        client.close()
    result = interpret(answer.data if isinstance(answer.data, dict) else {})
    result["model"] = cfg["model"]
    return result


__all__ = ["SCHEMA", "SYSTEM", "available", "interpret", "needle_range", "prepare_photo", "read_ball_band",
           "weight_category"]
