"""Find per-size values in pattern text ("AI marks, code copies").

The AI quotes an instruction word for word; this module finds the groups of per-size numbers inside such a quote
and copies them, as written, into the guide format's `sized_value` (guide-schema.json, version 0.2).

Standard library only, no network, deterministic. Values are never converted or repaired: "4½" stays "4½",
"three" stays "three", "65-70" stays "65-70". A list with the wrong number of values is returned as written, with
`length_ok` False and a note.

Notations handled (see the tests for examples of each):

* dash lists: "92-96-100 sts", "4½-4-3½", "250-300- 300 -350" (a highlighted size), "19-20-21 / 21-22-22",
  "71 - 76-81 - 86-91" (spaced dashes between sizes, tight dashes inside ranges), "2 - 3/4 - 5/6";
* a head value with a bracketed list: "66 (72, 78, 84)", "81 (91:102:112)", "40 [44:48:52]", "100 (108-114-122)",
  "81-86 (91-97:102-107)", "- (-, -, 0, 2)", "three (4, 5, 6)";
* alternating brackets, one size per number: "1 (2) 3 (4)", "65-70 (75-80) 85-90", "every 6th (8th) 10th row",
  "every 12th, (10th), 8th", "every 9. (8.) 7. row", "p (k) p (k)";
* grouped brackets: "(a, b, c) [d, e, f] {g, h, i}", with "X" or "n/a" meaning "not this size" ("-");
* label-prefixed lists "XS 82, S 86, M 90" (with `size_labels`);
* a plain table row "2 3 3 4 balls" (only when the count matches exactly);
* blocks per extra choice "fingering: 10 (12, 14); dk: 8 (9, 10)" (with `choice_labels`), kind "by_choice".
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

__all__ = ["SizedRun", "find_runs", "to_sized_value", "slot_text", "quantity", "UNITS"]

UNITS = ("stitches", "rows", "rounds", "row_pairs", "repeats", "times", "cm", "mm", "in", "m", "yd", "g", "oz",
         "balls", "skeins", "pieces", "other")


@dataclass
class SizedRun:
    start: int                 # character offset in the input text
    end: int                   # end offset (exclusive); text[start:end] == self.text
    text: str                  # the exact substring holding the values (and its unit, if adjacent)
    values: list[str | None]   # values as written, in size order ("-" = not this size); empty when by_choice
    unit: str | None           # one of UNITS, or None
    kind: str                  # "per_size" or "by_choice"
    by_choice: dict[str, list[str | None]] | None   # choice label -> per-size values, when kind == "by_choice"
    length_ok: bool            # True when every list has exactly n_sizes values
    note: str | None           # short plain-English note when something is odd
    # Offsets of the values alone, without a trailing unit; slot_text replaces this part. None means start/end.
    value_start: int | None = field(default=None, repr=False)
    value_end: int | None = field(default=None, repr=False)


# --------------------------------------------------------------------------------------------------------------
# Lexical pieces

_FR = "½¼¾⅓⅔⅛⅜⅝⅞⅕⅖⅗⅘⅙⅚"
_DASH = "-–—−"
_DASH_RX = r"\-–—−"  # for use inside regex character classes
_OPEN = "([{"
_CLOSE = ")]}"
_INCH = "”″\""

# A number as written: "4", "4.5", "4,5", "4½", "17 ½", "4 1/2", "3/4" (a label such as children's "3/4"), "½".
_NUM = (rf"(?:\d{{1,2}}/\d{{1,2}}(?![\d/])"
        rf"|\d+(?:[.,]\d+)?(?:[  ]?[{_FR}]|[  ]\d{{1,2}}/\d{{1,2}}(?![\d/]))?"
        rf"|[{_FR}])")
# A single value: a number with an optional ordinal suffix ("6th", or "9." as in "every 9. (8.) 7. row") and an
# optional inch mark ('6.9”').
_ORD = r"(?:(?<=1)st|(?<=2)nd|(?<=3)rd|th)(?![A-Za-z])"   # "1st", "2nd", "3rd", "4th" ("6st" is 6 stitches)
_ATOM = rf"(?:{_NUM})(?:{_ORD}|\.(?![\d\w]))?[{_INCH}]?"
_ATOM_ND = rf"(?:{_NUM})(?:{_ORD})?[{_INCH}]?"   # no "9." ordinal (dash lists, ranges)
_NUMWORDS = ("zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
             "sixteen|seventeen|eighteen|nineteen|twenty|once|twice")
_NUMWORD = rf"(?:{_NUMWORDS})(?![A-Za-z])"
_PLACEHOLDER = rf"(?:[{_DASH_RX}]{{1,2}}|[xX]|n/?a|N/?A)"
_STITCHWORD = r"(?:knit|purl|k|p)(?![A-Za-z0-9])"

_ATOM_RE = re.compile(_ATOM)
_ATOM_ND_RE = re.compile(_ATOM_ND)
_NUMWORD_RE = re.compile(_NUMWORD, re.IGNORECASE)
_STITCHWORD_RE = re.compile(_STITCHWORD, re.IGNORECASE)
_PIECE_RE = re.compile(
    rf"^(?:(?P<range>{_ATOM_ND}\s*[{_DASH_RX}]\s*{_ATOM_ND})|(?P<atom>{_ATOM})|(?P<word>{_NUMWORD})"
    rf"|(?P<ph>{_PLACEHOLDER}))$",
    re.IGNORECASE,
)
_ORDINAL_RE = re.compile(r"^\d+(?:st|nd|rd|th|\.)$", re.IGNORECASE)
_DASHSEP_RE = re.compile(rf"[ \t ]*[{_DASH_RX}][ \t ]*|[ \t ]*/[ \t ]+|[ \t ]+/[ \t ]*")
_ITEM_GAP_RE = re.compile(r"[ \t ]*(?:\n[ \t ]*)?(,)?[ \t ]*(?:\n[ \t ]*)?")

_ROW_WORD_BEFORE = re.compile(r"(?:\b(?:rows?|rounds?|rnds?|rds?|r|steps?|pages?|pp?\.?|fig\.?|figures?|"
                              r"charts?|diagrams?)\s*\.?\s*)$", re.IGNORECASE)
_PATTERN_NO_BEFORE = re.compile(r"(?:\b(?:drops|pattern|design|no\.?|nr\.?|ref\.?|art\.?|model|item|issue)"
                                r"\s*[#:]?\s*|#\s*)$", re.IGNORECASE)
_DATE_RE = re.compile(r"\d{4}[-–/]\d{1,2}[-–/]\d{1,2}|\d{1,2}[-–/]\d{1,2}[-–/]\d{4}")

# Unit words after a value. Longer forms first.
_UNIT_WORDS = [
    (r"row\s*pairs?|round\s*pairs?|rnd\s*pairs?", "row_pairs"),
    (r"stitches|stitch|sts|st(?:\(s\))?", "stitches"),
    (r"rows?(?:\(s\))?", "rows"),
    (r"rounds?(?:\(s\))?|rnds?(?:\(s\))?|rds", "rounds"),
    (r"repeats?|reps?(?:\(s\))?", "repeats"),
    (r"times?(?:\(s\))?", "times"),
    (r"cm|centimet(?:re|er)s?", "cm"),
    (r"mm|millimet(?:re|er)s?", "mm"),
    (r"inches|inch|ins|in(?=\s*(?:$|[.,;:)\]}/]|\s(?:from|long|wide|high|deep|across|ending|end|before|after|"
     r"or|and|\[|\()))", "in"),
    (r"metres|meters|mtrs?|m", "m"),
    (r"yards?|yds?", "yd"),
    (r"grams?|grammes?|gr|g", "g"),
    (r"ounces?|oz", "oz"),
    (r"balls?", "balls"),
    (r"skeins?|hanks?", "skeins"),
    (r"pieces?", "pieces"),
]
_UNIT_RE = re.compile(
    r"[ \t ]*(?:(?:more|new|additional|extra|total|remaining|rem\.?|further|other|full|whole|"
    r"pattern|patt)[ \t ]+)?(?:[A-Za-z]+-)?(?:"
    + "|".join(f"(?P<u{i}>{rx})" for i, (rx, _) in enumerate(_UNIT_WORDS))
    + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)

_UNIT_ALIASES = {
    "sts": "stitches", "st": "stitches", "stitch": "stitches", "stitches": "stitches",
    "row": "rows", "rows": "rows", "round": "rounds", "rounds": "rounds", "rnd": "rounds", "rnds": "rounds",
    "row_pairs": "row_pairs", "row pairs": "row_pairs", "round pairs": "row_pairs",
    "repeat": "repeats", "repeats": "repeats", "reps": "repeats", "time": "times", "times": "times",
    "cm": "cm", "mm": "mm", "in": "in", "inch": "in", "inches": "in", "ins": "in", '"': "in", "”": "in",
    "m": "m", "metres": "m", "meters": "m", "yd": "yd", "yds": "yd", "yards": "yd", "g": "g", "grams": "g",
    "oz": "oz", "ball": "balls", "balls": "balls", "skein": "skeins", "skeins": "skeins", "piece": "pieces",
    "pieces": "pieces", "other": "other",
}


def _norm_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    return _UNIT_ALIASES.get(unit.strip().lower(), unit if unit in UNITS else None)


def _unit_after(text: str, pos: int) -> tuple[str | None, int]:
    """The unit word right after a value (with an optional filler word: "more times", "new stitches",
    "shoulder-stitches"); returns (unit, end offset) or (None, pos)."""
    m = _UNIT_RE.match(text, pos)
    if not m:
        return None, pos
    for i, (_, unit) in enumerate(_UNIT_WORDS):
        if m.group(f"u{i}") is not None:
            return unit, m.end()
    return None, pos


def _ok_start(text: str, i: int) -> bool:
    """A number may start here: not glued to a word ("k2tog", "M1L", "A.1", "ai-485", "GSR4")."""
    if i <= 0:
        return True
    prev = text[i - 1]
    if prev.isalnum() or prev in "._/'’$£€#@" or prev in _FR:
        return False
    if prev in _DASH:
        before = text[i - 2] if i >= 2 else ""
        if before.isalpha() or before == "*":
            return False
    return True


def _prev_nonspace(text: str, i: int) -> str:
    j = i - 1
    while j >= 0 and text[j] in " \t \n":
        j -= 1
    return text[j] if j >= 0 else ""


def _clean_value(s: str) -> tuple[str, bool]:
    """Strip outer spaces and a trailing inch mark; map placeholders to "-". Returns (value, had_inch_mark)."""
    v = s.strip()
    inch = False
    if v and v[-1] in _INCH and len(v) > 1:
        v = v[:-1].rstrip()
        inch = True
    if re.fullmatch(_PLACEHOLDER, v, re.IGNORECASE):
        return "-", inch
    # inch marks inside a range: 4”-6”
    if any(c in v for c in _INCH):
        v2 = "".join(c for c in v if c not in _INCH)
        return v2, True
    return v, inch


# --------------------------------------------------------------------------------------------------------------
# Notation hints

def _notation_family(notation: str | None) -> str | None:
    """'dash', 'bracket' or None from the AI's free-text hint."""
    if not notation:
        return None
    h = notation.lower()
    if "dash" in h:
        return "dash"
    if re.search(r"[(\[{]", h):
        return "bracket"
    if re.search(r"\b\w+\s?[-–]\s?\w+\s?[-–]\s?\w+", h):
        return "dash"
    if any(w in h for w in ("paren", "bracket", "alternat")):
        return "bracket"
    return None


def _notation_grouped(notation: str | None) -> bool:
    return bool(notation) and bool(re.match(r"\s*[(\[{]", notation))


# --------------------------------------------------------------------------------------------------------------
# Candidates

@dataclass
class _Cand:
    start: int
    vend: int                      # end of the values (before any unit)
    values: list[str | None]
    matcher: str
    inch: bool = False
    notes: list[str] = field(default_factory=list)
    exact: bool = False
    by_choice: dict[str, list[str | None]] | None = None
    end: int = 0                   # end including unit (filled in later)
    unit: str | None = None
    vstart: int | None = None
    labelled: bool = False         # values already placed by size label


def _dash_candidates(text: str, n: int, family: str | None) -> list[_Cand]:
    out: list[_Cand] = []
    covered_until = -1
    for m in re.finditer(r"\d|[" + _FR + "]", text):
        i = m.start()
        if i < covered_until or not _ok_start(text, i):
            continue
        a = _ATOM_ND_RE.match(text, i)
        if not a:
            continue
        atoms = [(a.start(), a.end())]
        seps: list[str] = []
        pos = a.end()
        while True:
            s = _DASHSEP_RE.match(text, pos)
            if not s:
                break
            b = _ATOM_ND_RE.match(text, s.end())
            if not b or b.start() == b.end():
                break
            seps.append(s.group(0))
            atoms.append((b.start(), b.end()))
            pos = b.end()
        if len(atoms) < 2:
            continue
        covered_until = pos
        if not any(any(c in sep for c in _DASH) for sep in seps):
            continue  # only slashes: "1.75oz/50g", "40 / 80"
        k = len(atoms)
        start = atoms[0][0]
        if _DATE_RE.match(text, start) or _PATTERN_NO_BEFORE.search(text[max(0, start - 14):start]):
            continue
        before = text[max(0, start - 12):start]
        if k == 2 and (n != 2 or family == "bracket" or _ROW_WORD_BEFORE.search(before)):
            continue
        raw = [text[s:e] for s, e in atoms]
        interp_all = [_clean_value(v) for v in raw]
        interps = [[v for v, _ in interp_all]]
        inch = any(f for _, f in interp_all)
        # Spaced dashes between sizes, tight dashes inside ranges ("71 - 76-81 - 86-91").
        kinds = ["tight" if (sep.strip() in _DASH and sep == sep.strip())
                 else "spaced" if (sep[:1].isspace() and sep[-1:].isspace()) else "half" for sep in seps]
        if "tight" in kinds and ("spaced" in kinds or any("/" in sep for sep in seps)):
            groups, cur = [], [0]
            for idx, kind in enumerate(kinds):
                if kind == "tight" and "/" not in seps[idx]:
                    cur.append(idx + 1)
                else:
                    groups.append(cur)
                    cur = [idx + 1]
            groups.append(cur)
            if all(len(g) <= 2 for g in groups):
                interps.append([_clean_value(text[atoms[g[0]][0]:atoms[g[-1]][1]])[0] for g in groups])
        chosen = next((iv for iv in interps if len(iv) == n), interps[0])
        exact = len(chosen) == n
        if not exact and family == "bracket":
            continue
        if not exact and k < 3:
            continue
        out.append(_Cand(start, pos, chosen, "dash", inch=inch, exact=exact))
    return out


def _parse_group(text: str, p: int, mode: str):
    """A bracket group at p whose content is only values. Returns (end, alternatives, inch, stray) or None."""
    if p >= len(text) or text[p] not in _OPEN:
        return None
    j = p
    stray = False
    if j + 1 < len(text) and text[j + 1] in _OPEN:
        j += 1
        stray = True
    k = j + 1
    while k < len(text) and k - j < 160:
        c = text[k]
        if c in _OPEN:
            return None
        if c in _CLOSE:
            break
        k += 1
    else:
        return None
    if k >= len(text) or text[k] not in _CLOSE:
        return None
    alts, inch = _content_alternatives(text[j + 1:k], mode)
    if not alts:
        return None
    return k + 1, alts, inch, stray


def _piece_value(piece: str):
    """A cleaned value when the piece is one value (number, range, number word or placeholder), else None."""
    s = piece.strip()
    if not s or not _PIECE_RE.match(s):
        return None
    return _clean_value(s)


def _content_alternatives(content: str, mode: str):
    s = content.strip()
    if not s:
        return None, False
    if mode == "stitch":
        if _STITCHWORD_RE.fullmatch(s):
            return [[s]], False
        return None, False
    alts: list[list[str]] = []
    inch = False

    def add(pieces):
        nonlocal inch
        vals = []
        for pc in pieces:
            pv = _piece_value(pc)
            if pv is None:
                return
            vals.append(pv[0])
            inch = inch or pv[1]
        if vals and vals not in alts:
            alts.append(vals)

    if re.search(r"[;:]|,\s", s):
        add(re.split(r"\s*(?:[;:]|,(?=\s))\s*", s))
    elif "," in s:
        add(s.split(","))
        add([s])
    else:
        add([s])  # a single value or a single range
        parts = re.split(rf"(\s*[{_DASH_RX}]\s*)", s)
        atoms, seps = parts[0::2], parts[1::2]
        if len(atoms) >= 2 and all(a.strip() for a in atoms):
            add(atoms)
            if any(sp != sp.strip() for sp in seps) and any(sp == sp.strip() for sp in seps):
                groups, cur = [], atoms[0]
                for sp, at in zip(seps, atoms[1:]):
                    if sp == sp.strip():
                        cur += sp + at
                    else:
                        groups.append(cur)
                        cur = at
                groups.append(cur)
                add(groups)
    return (alts or None), inch


def _parse_bare(text: str, p: int, first: bool, mode: str):
    """A bare value at p (not in brackets). Returns (end, value, inch, is_placeholder) or None."""
    if p >= len(text):
        return None
    if mode == "stitch":
        m = _STITCHWORD_RE.match(text, p)
        if m and (p == 0 or not text[p - 1].isalnum()):
            return m.end(), m.group(0), False, False
        return None
    c = text[p]
    if c in _DASH:
        m = re.compile(rf"[{_DASH_RX}]{{1,2}}(?![\d{_FR}])").match(text, p)
        if m and not re.match(r"[ \t]*\d", text[m.end():m.end() + 3]):
            return m.end(), "-", False, True
        return None
    if first and c.isalpha():
        m = _NUMWORD_RE.match(text, p)
        if m and (p == 0 or not text[p - 1].isalnum()):
            return m.end(), m.group(0), False, False
        return None
    if not _ok_start(text, p):
        return None
    a = _ATOM_RE.match(text, p)
    if not a or a.start() == a.end():
        return None
    end = a.end()
    r = re.compile(rf"[ \t ]*[{_DASH_RX}][ \t ]*(?={_ATOM_ND})").match(text, a.end())
    if r and not text[a.start():a.end()].endswith("."):
        b = _ATOM_ND_RE.match(text, r.end())
        if b:
            if re.compile(rf"[ \t ]*[{_DASH_RX}][ \t ]*\d").match(text, b.end()):
                return None  # part of a dash list
            end = b.end()
    v, inch = _clean_value(text[p:end])
    return end, v, inch, False


def _chain_at(text: str, p: int, mode: str):
    """Bracket chains: "a (b, c)", "a (b) c (d)", "(a, b) [c, d]", "a [b:c]". Returns a raw chain or None.

    Each item is (start, end, kind, alternatives, inch, stray, comma_before, loose): kind "g" for a bracket
    group, "b" for a bare value; `loose` marks one bare value that follows another bare value without brackets
    (kept only when it makes the count right, e.g. "9 (11) 13 (13) 16 18 times")."""
    items = []
    pos = p
    while True:
        comma = False
        q = pos
        if items:
            g = _ITEM_GAP_RE.match(text, pos)
            q = g.end()
            comma = bool(g.group(1))
        grp = _parse_group(text, q, mode)
        if grp:
            end, alts, inch, stray = grp
            items.append((q, end, "g", alts, inch, stray, comma, False))
            pos = end
            continue
        if items and items[-1][2] == "g" and all(len(a) >= 2 for a in items[-1][3]):
            break  # "a (b, c, d)" ends at its bracket
        loose = bool(items) and items[-1][2] == "b"
        if loose and (comma or "\n" in text[pos:q] or mode != "value"):
            break
        bare = _parse_bare(text, q, not items, mode)
        if not bare:
            break
        end, v, inch, ph = bare
        if loose and ph:
            break
        items.append((q, end, "b", [[v]], inch, False, comma, loose))
        pos = end
        if loose:
            break
    # A bare placeholder must be followed by a group.
    cleaned = []
    for idx, it in enumerate(items):
        if it[2] == "b" and it[3] == [["-"]] and not (idx + 1 < len(items) and items[idx + 1][2] == "g"):
            break
        cleaned.append(it)
    items = cleaned
    if not items or not any(it[2] == "g" for it in items):
        return None
    if items[0][2] == "g":
        prev = _prev_nonspace(text, items[0][0])
        if prev and (prev.isdigit() or prev in _FR or prev in _INCH):
            return None
    return items


def _choose_values(items, n: int):
    """Pick one interpretation per item so that the count matches n when possible."""
    alt_lists = [it[3] for it in items]
    combos_count = 1
    for a in alt_lists:
        combos_count *= len(a)
    bare_ranges = any(it[2] == "b" and re.search(rf"\d\s*[{_DASH_RX}]\s*\d", it[3][0][0]) for it in items)

    def default(alts):
        if len(alts) == 1:
            return alts[0]
        # prefer splitting into several values unless the head values are ranges
        multi = [a for a in alts if len(a) > 1]
        single = [a for a in alts if len(a) == 1]
        if bare_ranges and single and multi and len(multi[0]) == 2:
            return single[0]
        return max(alts, key=len)

    defaults = [default(a) for a in alt_lists]
    best = [v for d in defaults for v in d]
    if len(best) == n or combos_count > 512:
        return best
    exact = []
    for combo in itertools.product(*alt_lists):
        vals = [v for c in combo for v in c]
        if len(vals) == n:
            ranges = sum(1 for v in vals if re.search(rf"\d\s*[{_DASH_RX}]\s*\d", v or ""))
            consistent = ranges in (0, len(vals))
            dist = sum(1 for c, d in zip(combo, defaults) if c != d)
            exact.append((not consistent, dist, vals))
    if exact:
        exact.sort(key=lambda t: (t[0], t[1]))
        return exact[0][2]
    return best


def _chain_candidates(text: str, n: int, family: str | None, grouped: bool, mode: str) -> list[_Cand]:
    raw = []
    starts = set()
    for m in re.finditer(r"[\d" + _FR + _DASH_RX + r"(\[{]|[A-Za-z]", text):
        i = m.start()
        if i in starts:
            continue
        if text[i].isalpha():
            if mode == "stitch":
                if not _STITCHWORD_RE.match(text, i) or (i > 0 and text[i - 1].isalnum()):
                    continue
            elif not _NUMWORD_RE.match(text, i) or (i > 0 and text[i - 1].isalnum()):
                continue
        items = _chain_at(text, i, mode)
        if not items:
            continue
        raw.append(items)
    # drop chains contained in a longer chain (maximal munch)
    spans = [(it[0][0], it[-1][1]) for it in raw]
    out: list[_Cand] = []
    for idx, items in enumerate(raw):
        s, e = spans[idx]
        if any((s2 <= s and e <= e2) and (s2, e2) != (s, e) for s2, e2 in spans):
            continue
        if spans.index((s, e)) != idx:
            continue
        notes = []
        # commas between items only for ordinal lists ("every 12th, (10th), 8th")
        values_flat = [v for it in items for alt in it[3][:1] for v in alt]
        if any(it[6] for it in items[1:]) and not all(_ORDINAL_RE.match(v or "") for v in values_flat):
            cut = next(k for k, it in enumerate(items) if k > 0 and it[6])
            items = items[:cut]
            if not any(it[2] == "g" for it in items):
                continue
        if items[-1][7]:
            with_loose = _choose_values(items, n)
            if len(with_loose) == n and len(_choose_values(items[:-1], n)) != n and \
                    all(len(alt) == 1 for it in items if it[2] == "g" for alt in it[3][:1]):
                notes.append("brackets missing around a value")
            else:
                items = items[:-1]
        values = _choose_values(items, n)
        start, vend = items[0][0], items[-1][1]
        # "9. (8.) 7." keeps its dots only when every value has one
        dotted = [v for v in values if v and v.endswith(".") and v[:-1].isdigit()]
        if dotted and len(dotted) != len(values):
            values = [v[:-1] if v and v.endswith(".") and v[:-1].isdigit() else v for v in values]
            if text[vend - 1] == ".":
                vend -= 1
        if any(it[5] for it in items):
            notes.append("stray bracket")
        groups = [it for it in items if it[2] == "g"]
        bares = [it for it in items if it[2] == "b"]
        exact = len(values) == n
        if mode == "stitch":
            if not exact or len(values) < 2:
                continue
            if not bares:
                continue
        elif not bares:
            # only brackets: "(60, 66, 72)" or "(a, b) [c, d] {e, f}"
            if len(groups) == 1 and not (exact and len(values) >= 2) and not (grouped and len(values) >= 2):
                continue
            if len(groups) > 1 and any(len(alt) < 2 for g in groups for alt in g[3][:1]) and not exact:
                continue
        if not exact and family == "dash":
            continue
        out.append(_Cand(start, vend, values, "chain" if mode == "value" else "stitch",
                         inch=any(it[4] for it in items), notes=notes, exact=exact))
    return out


def _table_candidates(text: str, n: int) -> list[_Cand]:
    """A plain table row: "2 3 3 4 balls" with exactly n numbers separated by spaces."""
    if n < 3:
        return []
    out = []
    rx = re.compile(rf"(?<![\d{_FR}.,/\-–])(?:{_ATOM_ND})(?:[ \t ]+(?:{_ATOM_ND}))+(?![\d{_FR}])")
    for m in rx.finditer(text):
        if not _ok_start(text, m.start()):
            continue
        parts = re.split(r"[ \t ]+", m.group(0))
        # "17 ½" is one value
        merged: list[str] = []
        for part in parts:
            if merged and part in _FR:
                merged[-1] += " " + part
            else:
                merged.append(part)
        if len(merged) != n:
            continue
        after = text[m.end():m.end() + 2]
        if after[:1] in _DASH or after[:1] in _OPEN or after.strip()[:1] in _OPEN:
            continue
        before = _prev_nonspace(text, m.start())
        if before in _DASH:
            continue
        vals = [_clean_value(v)[0] for v in merged]
        out.append(_Cand(m.start(), m.end(), vals, "table", exact=True))
    return out


def _label_candidates(text: str, n: int, size_labels: list[str] | None) -> list[_Cand]:
    """ "XS 82, S 86, M 90" using the size labels."""
    if not size_labels:
        return []
    labels = [lb for lb in size_labels if lb and re.search(r"[A-Za-z]", lb) and not re.search(r"\s", lb)]
    if len(labels) < 2:
        return []
    index = {lb: i for i, lb in enumerate(size_labels)}
    alt = "|".join(re.escape(lb) for lb in sorted(labels, key=len, reverse=True))
    item_rx = re.compile(
        rf"(?<![\w])(?P<label>{alt})(?:[ \t ]*[:=][ \t ]*|[ \t ]+)"
        rf"(?P<val>{_ATOM_ND}(?:[ \t ]*[{_DASH_RX}][ \t ]*{_ATOM_ND})?)(?![\w])"
    )
    gap_rx = re.compile(r"[ \t ]*(?:[A-Za-z]{1,6}\.?[ \t ]*)?[,;/|][ \t ]*|[ \t ]+")
    out = []
    pos = 0
    while True:
        m = item_rx.search(text, pos)
        if not m:
            break
        items = [m]
        cur = m
        while True:
            unit, uend = _unit_after(text, cur.end())
            g = gap_rx.match(text, uend if unit else cur.end())
            if not g:
                break
            nxt = item_rx.match(text, g.end())
            if not nxt:
                break
            items.append(nxt)
            cur = nxt
        pos = cur.end()
        if len(items) < 2:
            continue
        values: list[str | None] = [None] * n
        notes = []
        for it in items:
            i = index[it.group("label")]
            if i >= n:
                continue
            if values[i] is not None:
                notes.append(f"size {it.group('label')} given twice")
            values[i] = _clean_value(it.group("val"))[0]
        given = sum(v is not None for v in values)
        exact = given == n
        if not exact:
            notes.append(f"values for {given} of {n} sizes")
        c = _Cand(items[0].start(), items[-1].end(), values, "label", notes=notes, exact=exact, labelled=True)
        out.append(c)
    return out


def _label_range_candidates(text: str, n: int, size_labels: list[str] | None) -> list[_Cand]:
    """Values tagged with the sizes they belong to: "row 17 (S - XL) / row 19 (XXL - XXXL)",
    "4 (XS, S) and 5 (M - XL)"."""
    if not size_labels:
        return []
    labels = [lb for lb in size_labels if lb and re.search(r"[A-Za-z]", lb) and not re.search(r"\s", lb)]
    if len(labels) < 2:
        return []
    index = {lb: i for i, lb in enumerate(size_labels)}
    alt = "|".join(re.escape(lb) for lb in sorted(labels, key=len, reverse=True))
    lab = rf"(?<![\w])(?:{alt})(?![\w])"
    item_rx = re.compile(
        rf"(?P<val>{_ATOM_ND}(?:[ \t\u00a0]*[{_DASH_RX}][ \t\u00a0]*{_ATOM_ND})?)[ \t\u00a0]*"
        rf"\([ \t\u00a0]*(?:sizes?[ \t\u00a0]+)?(?P<labs>{lab}(?:[ \t\u00a0]*(?:[{_DASH_RX},/&+]|and|to)"
        rf"[ \t\u00a0]*{lab})*)(?:[ \t\u00a0]*[,;][^()\[\]{{}}\d]*)?[ \t\u00a0]*\)"
    )
    gap_rx = re.compile(r"[ \t\u00a0]*(?:[/,;]|\band\b|\bor\b)[ \t\u00a0]*(?:[A-Za-z]+[ \t\u00a0]+){0,2}")
    out = []
    pos = 0
    while True:
        m = item_rx.search(text, pos)
        if not m:
            break
        if not _ok_start(text, m.start()):
            pos = m.start() + 1
            continue
        items = [m]
        cur = m
        while True:
            g = gap_rx.match(text, cur.end())
            nxt = item_rx.match(text, g.end()) if g else None
            if not nxt:
                break
            items.append(nxt)
            cur = nxt
        pos = cur.end()
        if len(items) < 2:
            continue
        values: list[str | None] = [None] * n
        notes: list[str] = []
        ok = True
        for it in items:
            names = re.findall(lab, it.group("labs"))
            joins = re.findall(rf"[{_DASH_RX}]|\bto\b", it.group("labs"))
            idxs = [index[x] for x in names if x in index]
            if not idxs:
                ok = False
                break
            span = range(min(idxs), max(idxs) + 1) if joins and len(idxs) == 2 else idxs
            for i in span:
                if i < n:
                    if values[i] is not None:
                        notes.append("a size is given twice")
                    values[i] = _clean_value(it.group("val"))[0]
        if not ok:
            continue
        given = sum(v is not None for v in values)
        exact = given == n
        if not exact:
            notes.append(f"values for {given} of {n} sizes")
        out.append(_Cand(items[0].start(), items[-1].end(), values, "label", notes=notes, exact=exact,
                         labelled=True))
    return out


def _finish(text: str, c: _Cand, n: int) -> SizedRun:
    unit, end = _unit_after(text, c.vend)
    if c.inch and unit is None:
        unit = "in"
    if c.unit is not None:
        unit, end = c.unit, max(end, c.end)
    notes = list(c.notes)
    if re.search(r"\bsizes?\s*:?\s*$", text[max(0, c.start - 8):c.start], re.IGNORECASE):
        notes.append("follows the word size: these may be size labels, not quantities")
    if c.by_choice is not None:
        bad = [f"{len(v)} values for {n} sizes ({lb})" for lb, v in c.by_choice.items() if len(v) != n]
        length_ok = not bad
        notes.extend(bad)
        values: list[str | None] = []
        kind = "by_choice"
    else:
        values = c.values
        length_ok = len(values) == n and not (c.labelled and not c.exact)
        if len(values) != n:
            notes.append(f"{len(values)} values for {n} sizes")
        kind = "per_size"
    if end <= c.vend:
        end = c.vend
    return SizedRun(
        start=c.start, end=end, text=text[c.start:end], values=values, unit=unit, kind=kind,
        by_choice=c.by_choice, length_ok=length_ok, note="; ".join(dict.fromkeys(notes)) or None,
        value_start=c.vstart if c.vstart is not None else c.start, value_end=c.vend,
    )


def _select(cands: list[_Cand]) -> list[_Cand]:
    order = sorted(cands, key=lambda c: (c.matcher != "by_choice", not c.exact, -(c.vend - c.start), c.start))
    chosen: list[_Cand] = []
    for c in order:
        if any(c.start < o.vend and o.start < c.vend for o in chosen):
            continue
        chosen.append(c)
    return sorted(chosen, key=lambda c: c.start)


def _choice_candidates(text: str, n: int, notation, size_labels, choice_labels) -> list[_Cand]:
    if not choice_labels:
        return []
    alt = "|".join(re.escape(lb) for lb in sorted(choice_labels, key=len, reverse=True))
    occ = list(re.finditer(rf"(?<![\w])(?P<label>{alt})[ \t ]*:", text, re.IGNORECASE))
    if not occ:
        return []
    canon = {lb.lower(): lb for lb in choice_labels}
    out: list[_Cand] = []
    block: dict[str, list[str | None]] = {}
    bstart = bend = None
    notes: list[str] = []
    unit = None

    def close():
        nonlocal block, bstart, bend, notes, unit
        if block:
            c = _Cand(bstart, bend, [], "by_choice", notes=notes, exact=True, by_choice=block)
            c.unit, c.end = unit, bend
            out.append(c)
        block, bstart, bend, notes, unit = {}, None, None, [], None

    for k, m in enumerate(occ):
        seg_end = occ[k + 1].start() if k + 1 < len(occ) else len(text)
        seg = text[m.end():seg_end]
        label = canon.get(m.group("label").lower(), m.group("label"))
        runs = _find_runs_plain(seg, n, notation=notation, size_labels=size_labels) if n > 1 else []
        if runs:
            r = runs[0]
            vals, vend, u = r.values, m.end() + r.end, r.unit
            if r.note:
                notes.append(f"{label}: {r.note}")
        else:
            single = re.search(rf"(?<![\w.,/]){_ATOM_ND}(?:[ \t ]*[{_DASH_RX}][ \t ]*{_ATOM_ND})?"
                               rf"|(?<![\w])(?:{_NUMWORDS})(?![\w])|(?<![\w])n/a(?![\w])", seg, re.IGNORECASE)
            if not single or seg[:single.start()].strip() not in ("",):
                close()
                continue
            v = _clean_value(single.group(0))[0]
            vals = [v] * n
            u, uend = _unit_after(seg, single.end())
            vend = m.end() + (uend if u else single.end())
            if n > 1:
                notes.append(f"{label}: one value for every size")
        if label in block:
            close()
        if bstart is None:
            bstart = m.start()
            unit = u
        block[label] = list(vals)
        bend = vend
        if unit is None:
            unit = u
    close()
    return out


def _find_runs_plain(text: str, n: int, *, notation=None, size_labels=None) -> list[SizedRun]:
    family = _notation_family(notation)
    grouped = _notation_grouped(notation)
    cands = []
    cands += _label_candidates(text, n, size_labels)
    cands += _label_range_candidates(text, n, size_labels)
    cands += _chain_candidates(text, n, family, grouped, "value")
    cands += _chain_candidates(text, n, family, grouped, "stitch")
    cands += _dash_candidates(text, n, family)
    cands += _table_candidates(text, n)
    return [_finish(text, c, n) for c in _select(cands)]


def find_runs(text: str, n_sizes: int, *, notation: str | None = None,
              size_labels: list[str] | None = None, choice_labels: list[str] | None = None) -> list[SizedRun]:
    """Every per-size group of values in `text`, left to right, not overlapping.

    n_sizes == 1: return [] (nothing is per-size), except by_choice blocks when choice_labels are given. `notation` is a free-text hint from the AI ("dash list",
    "a (b, c)", "a (b) c (d)", "(a, b, c) [d, e, f]", "a [b:c:d]"); it decides between readings when the count
    does not, but the text is always parsed on its own. `size_labels` enables "XS 82, S 86" lists.
    `choice_labels` (e.g. ["fingering", "dk"]) enables blocks like "fingering: 10 (12, 14); dk: 8 (9, 10)",
    returned as one run with kind "by_choice"."""
    if not text or n_sizes is None or n_sizes < 1 or (n_sizes == 1 and not choice_labels):
        return []
    n = n_sizes
    choice = _choice_candidates(text, n, notation, size_labels, choice_labels)
    plain = _find_runs_plain(text, n, notation=notation, size_labels=size_labels) if n > 1 else []
    runs = [_finish(text, c, n) for c in choice]
    for r in plain:
        if not any(r.start < c.end and c.start < r.end for c in runs):
            runs.append(r)
    runs.sort(key=lambda r: r.start)
    # "10 (12) cm [4 (4¾) in]": the bracketed list repeats the previous one in another unit.
    for prev, cur in zip(runs, runs[1:]):
        if (re.fullmatch(r"\s*[(\[{]\s*", text[prev.end:cur.start]) and prev.unit and cur.unit
                and prev.unit != cur.unit):
            note = "unit conversion of the previous value"
            cur.note = f"{note}; {cur.note}" if cur.note else note
    return runs


# --------------------------------------------------------------------------------------------------------------
# sized_value helpers

def to_sized_value(run: SizedRun | None, n_sizes: int, *, text: str | None = None, single: str | None = None,
                   unit: str | None = None, from_picture: bool = False,
                   choice_ids: dict[str, str] | None = None) -> dict:
    """A 0.2 `sized_value` dict. From a run: by_size (or by_choice, with labels mapped to ids by choice_ids).
    Without a run: `single` gives all=single; otherwise the value is "not given" (all/by_size/by_choice None).
    text defaults to run.text, then `text`. alt is always None (conversions are handled elsewhere)."""
    out = {
        "text": (text if text is not None else (run.text if run is not None else "")) or "",
        "unit": _norm_unit(unit) if unit is not None else (run.unit if run is not None else None),
        "all": None,
        "by_size": None,
        "by_choice": None,
        "from_picture": bool(from_picture),
        "alt": None,
    }
    if run is not None and text is None:
        out["text"] = run.text
    if run is not None:
        if run.kind == "by_choice" and run.by_choice is not None:
            ids = choice_ids or {}
            out["by_choice"] = [{"choice": ids.get(label, label), "by_size": list(vals)}
                                for label, vals in run.by_choice.items()]
        else:
            out["by_size"] = list(run.values)
    elif single is not None:
        out["all"] = single
    return out


def slot_text(text: str, runs: list[SizedRun], n_sizes: int, *, prefix: str = "s") -> tuple[str, list[dict]]:
    """Replace each run's values in text by {s1}, {s2}, ... and return (new_text, slots), where slots are
    [{"name": "s1", "value": <sized_value>}, ...] as in the schema's `slot`. A unit after the values stays in
    the text ("{s1} sts"); a by_choice block is replaced as a whole."""
    ordered = sorted(runs, key=lambda r: r.start)
    pieces = []
    slots = []
    pos = 0
    for i, r in enumerate(ordered, 1):
        name = f"{prefix}{i}"
        vs = r.value_start if r.value_start is not None else r.start
        ve = r.value_end if (r.value_end is not None and r.kind != "by_choice") else r.end
        if r.kind == "by_choice":
            vs = r.start
        if vs < pos:
            continue
        pieces.append(text[pos:vs])
        pieces.append("{" + name + "}")
        pos = ve
        slots.append({"name": name, "value": to_sized_value(r, n_sizes)})
    pieces.append(text[pos:])
    return "".join(pieces), slots


_SINGLE_RE = re.compile(
    rf"(?P<v>{_ATOM}(?:[ \t ]*[{_DASH_RX}][ \t ]*{_ATOM_ND})?)|(?<![A-Za-z])(?P<w>{_NUMWORDS})(?![A-Za-z])",
    re.IGNORECASE,
)


def _singles(text: str):
    """Single numbers (or ranges, or number words) with their unit: [(start, value_end, value, unit, end)]."""
    out = []
    for m in _SINGLE_RE.finditer(text):
        s = m.start()
        if m.group("v") is not None:
            if not _ok_start(text, s):
                continue
            raw = m.group("v")
            # "4." at the end of a sentence is not an ordinal
            if raw.endswith(".") and raw[:-1].isdigit():
                raw = raw[:-1]
            if raw[:1] in _DASH:
                continue
            vend = s + len(raw)
        else:
            if s > 0 and text[s - 1].isalnum():
                continue
            raw = m.group("w")
            vend = m.end()
        value, inch = _clean_value(raw)
        unit, end = _unit_after(text, vend)
        if inch and unit is None:
            unit = "in"
        out.append((s, vend, value, unit, end if unit else vend))
    return out


_RESULT_BEFORE = re.compile(r"(?:=|\btotal of|\bhave|\bremain(?:ing|s)?|\bleaves?|\bleft with|\bthere are)"
                            r"[\s:]*(?:a total of\s*)?$", re.IGNORECASE)
_EVERY_BEFORE = re.compile(r"\bevery\s*(?:other\s*)?$", re.IGNORECASE)
_UNTIL_ROW_BEFORE = re.compile(r"\b(?:until|to|through|up to|ending with|end(?:ing)? on)\s+(?P<u>rows?|rounds?|rnds?)"
                               r"\s*$", re.IGNORECASE)


def quantity(quote: str | None, n_sizes: int, *, notation: str | None = None, prefer_unit: str | None = None,
             size_labels: list[str] | None = None, choice_labels: list[str] | None = None,
             choice_ids: dict[str, str] | None = None, from_picture: bool = False) -> dict | None:
    """The sized_value of a short quote that gives ONE quantity: "work 6-8-10 rounds", "until piece measures
    30 cm", "repeat 3 (4, 5) times", "= 164 (176) sts", "every 4th row". A per-size run wins (the one in
    prefer_unit when there are several; among several stitch counts, the one after "=" or "a total of");
    otherwise the single number becomes `all`, preferring prefer_unit, then "until row N", then the first
    number with a unit. None when the quote is None or has no number."""
    if quote is None:
        return None
    want = _norm_unit(prefer_unit) if prefer_unit else None
    runs = find_runs(quote, n_sizes, notation=notation, size_labels=size_labels, choice_labels=choice_labels)

    def sv(run):
        return to_sized_value(run, n_sizes, from_picture=from_picture, choice_ids=choice_ids)

    if runs:
        matching = [r for r in runs if r.unit == want] if want else []
        if len(matching) > 1:
            result = [r for r in matching if _RESULT_BEFORE.search(quote[max(0, r.start - 20):r.start])]
            return sv(result[-1] if result else matching[0])
        if matching:
            return sv(matching[0])
        if not want:
            return sv(next((r for r in runs if r.unit), runs[0]))
    singles = [s for s in _singles(quote) if not any(r.start <= s[0] < r.end for r in runs)]

    def single(hit, unit):
        return to_sized_value(None, n_sizes, text=quote[hit[0]:hit[4]], single=hit[2], unit=unit,
                              from_picture=from_picture)

    if want and singles:
        tiers = [[], [], []]
        for sg in singles:
            before = quote[max(0, sg[0] - 20):sg[0]]
            until = _UNTIL_ROW_BEFORE.search(before)
            if sg[3] == want and not _EVERY_BEFORE.search(before):
                tiers[0].append(sg)
            elif until and _norm_unit(until.group("u").rstrip("s") + "s") == want:
                tiers[1].append(sg)
            elif sg[3] == want:
                tiers[2].append(sg)
        for tier in tiers:
            if tier:
                return single(tier[0], want)
    if runs:
        return sv(next((r for r in runs if r.unit), runs[0]))
    if not singles:
        return None
    # Skip row references ("Rows 1-4", "row 3") when something else is there.
    plain = [sg for sg in singles if not _ROW_WORD_BEFORE.search(quote[max(0, sg[0] - 12):sg[0]])] or singles
    hit = next((sg for sg in plain if sg[3]), plain[0])
    return single(hit, hit[3] if hit[3] else want)
