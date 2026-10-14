"""Numbers and units as knitting patterns write them.

Pure functions, standard library only. Guides keep every value as the string the pattern wrote ("4½", "4,5",
"three", "65-70"); this module turns such strings into numbers and converts between units when the app needs to
calculate (progress bars, metric display, needle look-ups). Nothing here is ever written back into a guide.
"""

from __future__ import annotations

import math
import re

__all__ = [
    "parse_number",
    "parse_range",
    "to_cm",
    "to_metres",
    "to_grams",
    "needle_mm",
    "gauge_per_10cm",
    "round_pairs_to_rounds",
    "cable_length_cm",
    "display_cm",
    "STANDARD_CABLE_LENGTHS_CM",
    "US_NEEDLE_MM",
    "UK_NEEDLE_MM",
]

FRACTIONS = {
    "½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅕": 0.2, "⅖": 0.4, "⅗": 0.6, "⅘": 0.8,
    "⅙": 1 / 6, "⅚": 5 / 6, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}

NUMBER_WORDS = {
    "zero": 0, "no": 0, "one": 1, "once": 1, "a": 1, "an": 1, "two": 2, "twice": 2, "three": 3, "thrice": 3,
    "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
}
# "a"/"an"/"no" are only accepted on their own ("a" alone is not a useful number), so keep them out of the
# public word list used by parse_number.
_WORDS_FOR_PARSE = {k: v for k, v in NUMBER_WORDS.items() if k not in ("a", "an", "no")}

_FRAC_CHARS = "".join(FRACTIONS)
_INCH_MARKS = "\"”″“'’"
_DASHES = "-–—−"

_NUM_RE = re.compile(
    rf"""^
    (?P<int>\d+)?
    (?:(?P<sep>[.,])(?P<dec>\d+))?
    (?:\s*(?P<frac>[{_FRAC_CHARS}])|\s+(?P<num>\d+)\s*/\s*(?P<den>\d+))?
    $""",
    re.VERBOSE,
)
_SLASH_RE = re.compile(r"^(?P<num>\d+)\s*/\s*(?P<den>\d+)$")
_ORDINAL_RE = re.compile(r"^(\d+)(?:st|nd|rd|th|\.)$", re.IGNORECASE)


def parse_number(s: str) -> float | None:
    """A single number as a pattern writes it, or None.

    "4½" -> 4.5, "4,5" -> 4.5, "17 ½" -> 17.5, "three" -> 3.0, "1/2" -> 0.5, "1 1/2" -> 1.5, "6th" -> 6.0,
    '6.9”' -> 6.9, "1,240" -> 1240.0 (three digits after a comma are read as a thousands separator).
    A range ("65-70"), a placeholder ("-", "X", "n/a") or anything else gives None.
    """
    if s is None:
        return None
    t = s.strip().rstrip(_INCH_MARKS).strip()
    if not t:
        return None
    low = t.lower()
    if low in _WORDS_FOR_PARSE:
        return float(_WORDS_FOR_PARSE[low])
    m = _ORDINAL_RE.match(t)
    if m:
        return float(m.group(1))
    m = _SLASH_RE.match(t)
    if m:
        den = int(m.group("den"))
        return int(m.group("num")) / den if den else None
    m = _NUM_RE.match(t)
    if not m or not (m.group("int") or m.group("frac")):
        return None
    if m.group("dec") is not None and m.group("int") is None:
        return None
    value = float(m.group("int") or 0)
    if m.group("dec") is not None:
        dec = m.group("dec")
        if m.group("sep") == "," and len(dec) == 3 and m.group("int") and m.group("int") != "0":
            value = value * 1000 + int(dec)  # thousands separator: "1,240 yds"
        else:
            value += float("0." + dec)
    if m.group("frac"):
        value += FRACTIONS[m.group("frac")]
    elif m.group("num"):
        den = int(m.group("den"))
        if not den:
            return None
        value += int(m.group("num")) / den
    return value


_RANGE_RE = re.compile(rf"^(?P<a>.+?)\s*(?:[{_DASHES}]|\bto\b)\s*(?P<b>[^{_DASHES}]+)$", re.IGNORECASE)


def parse_range(s: str) -> tuple[float, float] | None:
    """ "65-70" -> (65.0, 70.0), "4–5" -> (4.0, 5.0), "4 to 5" -> (4.0, 5.0); a single number x -> (x, x)."""
    if s is None:
        return None
    t = s.strip()
    single = parse_number(t)
    if single is not None:
        return (single, single)
    m = _RANGE_RE.match(t)
    if not m:
        return None
    a, b = parse_number(m.group("a")), parse_number(m.group("b"))
    if a is None or b is None:
        return None
    return (a, b)


def _unit_key(unit: str) -> str:
    return (unit or "").strip().lower().rstrip(".")


_CM_FACTORS = {
    "cm": 1.0, "cms": 1.0, "centimetre": 1.0, "centimetres": 1.0, "centimeter": 1.0, "centimeters": 1.0,
    "mm": 0.1, "millimetre": 0.1, "millimetres": 0.1, "millimeter": 0.1, "millimeters": 0.1,
    "m": 100.0, "metre": 100.0, "metres": 100.0, "meter": 100.0, "meters": 100.0,
    "in": 2.54, "ins": 2.54, "inch": 2.54, "inches": 2.54, '"': 2.54, "”": 2.54, "″": 2.54, "“": 2.54,
    "yd": 91.44, "yds": 91.44, "yard": 91.44, "yards": 91.44,
}


def to_cm(value: float, unit: str) -> float | None:
    """A length in cm: inches (in, ins, inch, inches, ", ”), cm, mm, m, yards. None for an unknown unit."""
    factor = _CM_FACTORS.get(_unit_key(unit))
    return None if factor is None or value is None else value * factor


_M_FACTORS = {
    "m": 1.0, "metre": 1.0, "metres": 1.0, "meter": 1.0, "meters": 1.0, "mtr": 1.0, "mtrs": 1.0,
    "yd": 0.9144, "yds": 0.9144, "yard": 0.9144, "yards": 0.9144,
    "cm": 0.01, "km": 1000.0,
}


def to_metres(value: float, unit: str) -> float | None:
    """A yarn length in metres: yards (0.9144 m each) or metres. None for an unknown unit."""
    factor = _M_FACTORS.get(_unit_key(unit))
    return None if factor is None or value is None else value * factor


_G_FACTORS = {
    "g": 1.0, "gr": 1.0, "gram": 1.0, "grams": 1.0, "gramme": 1.0, "grammes": 1.0, "kg": 1000.0,
    "oz": 28.3495, "ozs": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
}


def to_grams(value: float, unit: str) -> float | None:
    """A weight in grams: ounces (28.3495 g each) or grams. None for an unknown unit."""
    factor = _G_FACTORS.get(_unit_key(unit))
    return None if factor is None or value is None else value * factor


# Needle size tables.
#
# US sizes: the Craft Yarn Council of America's "Standards & Guidelines for Crochet and Knitting", knitting
# needle size chart (https://www.craftyarncouncil.com/standards/hooks-and-needles). Where makers disagree
# (US 10¾ is sold as 7 mm by some brands; US 13 is sold as 9 mm), the CYC value is used.
US_NEEDLE_MM: dict[str, float] = {
    "0000": 1.25, "000": 1.5, "00": 1.75, "0": 2.0, "1": 2.25, "1.5": 2.5, "2": 2.75, "2.5": 3.0, "3": 3.25,
    "4": 3.5, "5": 3.75, "6": 4.0, "7": 4.5, "8": 5.0, "9": 5.5, "10": 6.0, "10.5": 6.5, "10.75": 7.0,
    "11": 8.0, "13": 9.0, "15": 10.0, "17": 12.75, "19": 15.0, "35": 19.0, "50": 25.0,
}
# UK and Canadian sizes: the old imperial (Standard Wire Gauge based) numbers, which run the opposite way to
# metric (a larger number is a thinner needle). Values follow the conversion table printed by the UK Hand
# Knitting Association / Craft Yarn Council chart (same source as above, "UK/Canadian" column); UK 9 is
# 3.75 mm there (3.5 mm has no exact old size).
UK_NEEDLE_MM: dict[str, float] = {
    "14": 2.0, "13": 2.25, "12": 2.75, "11": 3.0, "10": 3.25, "9": 3.75, "8": 4.0, "7": 4.5, "6": 5.0,
    "5": 5.5, "4": 6.0, "3": 6.5, "2": 7.0, "1": 7.5, "0": 8.0, "00": 9.0, "000": 10.0,
}

_SIZE_TOKEN = rf"(?P<size>\d+(?:[.,]\d+)?(?:\s?[{_FRAC_CHARS}])?)"
_MM_RE = re.compile(rf"(?<![\d.,])(?P<v>\d+(?:[.,]\d+)?(?:\s?[{_FRAC_CHARS}])?)\s*mm\b", re.IGNORECASE)
_US_RE = re.compile(rf"\bUS\s*(?:size\s*)?#?\s*{_SIZE_TOKEN}|#\s*{_SIZE_TOKEN.replace('size', 'size2')}\s*US\b",
                    re.IGNORECASE)
_UK_RE = re.compile(rf"\b(?:UK|Canadian|Can\.?|CA)\s*(?:size\s*)?#?\s*(?P<size>0{{1,3}}|\d+)\b", re.IGNORECASE)
_BARE_RE = re.compile(rf"(?:\bsize\s*#?|#)\s*{_SIZE_TOKEN}(?!\s*mm)", re.IGNORECASE)


def _us_key(token: str) -> str | None:
    value = parse_number(token)
    if value is None:
        return None
    if token.strip().startswith("0"):
        return token.strip()  # "00", "000"
    key = f"{value:g}"
    return key if key in US_NEEDLE_MM else None


def needle_mm(text: str) -> float | None:
    """A needle size in mm from text such as "4.5 mm", "4,5mm", "US 7", "US #3", "#9 US", "size 13",
    "UK 9" or "Canadian 8". A metric size wins when the text gives one. A bare "size N" or "#N" is read as
    a US size. None when no size is recognised."""
    if not text:
        return None
    m = _MM_RE.search(text)
    if m:
        return parse_number(m.group("v"))
    m = _UK_RE.search(text)
    if m:
        return UK_NEEDLE_MM.get(m.group("size"))
    m = _US_RE.search(text)
    if m:
        token = m.group("size") or m.group("size2")
        key = _us_key(token)
        return US_NEEDLE_MM.get(key) if key else None
    m = _BARE_RE.search(text)
    if m:
        key = _us_key(m.group("size"))
        return US_NEEDLE_MM.get(key) if key else None
    return None


def gauge_per_10cm(count: float, over_value: float, over_unit: str) -> float:
    """Stitches (or rows) per 10 cm, rounded to 0.1: 32 sts over 4 in -> 31.5; 8 sts per 1 in -> 31.5."""
    over_cm = to_cm(over_value, over_unit)
    if not over_cm:
        raise ValueError(f"cannot measure gauge over {over_value!r} {over_unit!r}")
    return round(count * 10.0 / over_cm, 1)


def round_pairs_to_rounds(n: float) -> float:
    """Round (or row) pairs to rounds: 27 round pairs -> 54 rounds."""
    return n * 2


STANDARD_CABLE_LENGTHS_CM = (20, 25, 30, 40, 50, 60, 80, 100, 120, 150)


def cable_length_cm(inches: float) -> int:
    """The nearest standard metric circular needle length: 16 in -> 40, 24 -> 60, 32 -> 80, 40 -> 100,
    47 -> 120, 12 -> 30. On a tie the shorter length is chosen."""
    cm = inches * 2.54
    return min(STANDARD_CABLE_LENGTHS_CM, key=lambda length: (abs(length - cm), length))


def _round_half_up(x: float) -> float:
    return math.floor(x + 0.5)


def display_cm(cm: float) -> str:
    """Knitter-friendly cm: under 10 cm to the nearest 0.5, otherwise to the whole cm. 4.4 -> "4.5",
    4.0 -> "4", 26.67 -> "27"."""
    if cm < 10:
        value = _round_half_up(cm * 2 + 1e-9) / 2
        if value >= 10:
            return "10"
    else:
        value = _round_half_up(cm + 1e-9)
    return f"{value:g}" if value != int(value) else str(int(value))
