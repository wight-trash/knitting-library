"""Prototype: knitting-pattern PDF text in reading order, from poppler `pdftotext -bbox-layout`.

Pipeline per document:
  1. words with boxes   (pdftotext -bbox-layout, parsed with ElementTree; poppler's own blocks are ignored)
  2. segments           (words left to right on one baseline, gap < 1 line height; rotated words kept apart)
  3. clutter removal    (margin URL/date/"Page x of y"/page numbers, margin lines repeated on most pages, TCPDF)
  4. tables             (2+ stacked rows of 3+ short cells become one atomic box, read row by row)
  5. reading order      (gutter first: an x where segments on both sides form columns; crossing segments cut
                         bands; column bands read left column then right, recursively; leftovers re-ordered;
                         no gutter -> split at full-width gaps of 2.5 line heights, else top-to-bottom rows)
  6. line joining       (a line ending "digit-" is joined to a next line starting with a digit, no space)
  7. character clean-up (ligatures, zero-width and soft hyphens, odd spaces)
  8. coverage           (non-space chars per page; ink share from a 160 px wide render)
  links via pypdf (BSD): URI + rectangle, anchor text = words under the rectangle.
Usage: python -I readpdf.py file.pdf [--json] [--pages 2-3] [--nocov]
Evaluation: python -I evaluate.py
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field

NS = "{http://www.w3.org/1999/xhtml}"


@dataclass(eq=False)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    words: list = field(default_factory=list)  # list[Box] for segments
    cells: list = field(default_factory=list)  # segments inside a table block

    @property
    def h(self):
        return self.y1 - self.y0

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


@dataclass
class Page:
    number: int
    width: float
    height: float
    words: list
    segments: list = field(default_factory=list)
    lines: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    chars: int = 0
    ink: float = 0.0          # fraction of page pixels that are not background
    ink_outside_text: float = 0.0
    status: str = ""


# ---------------------------------------------------------------- 1. words
def read_words(pdf: str, first: int | None = None, last: int | None = None) -> list[Page]:
    cmd = ["pdftotext", "-bbox-layout", "-enc", "UTF-8"]
    if first:
        cmd += ["-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    out = subprocess.run(cmd + [pdf, "-"], capture_output=True, check=True, timeout=120).stdout
    # poppler writes XHTML; strip the DOCTYPE so ElementTree never sees an external DTD reference
    out = re.sub(rb"<!DOCTYPE[^>]*>", b"", out, count=1)
    root = ET.fromstring(out)
    pages = []
    for i, pg in enumerate(root.iter(NS + "page")):
        words = []
        for w in pg.iter(NS + "word"):
            t = w.text or ""
            words.append(Box(float(w.get("xMin")), float(w.get("yMin")), float(w.get("xMax")),
                             float(w.get("yMax")), t))
        pages.append(Page((first or 1) + i, float(pg.get("width")), float(pg.get("height")), words))
    return pages


# ---------------------------------------------------------------- 7. characters
LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
             "ﬅ": "st", "ﬆ": "st"}
DROP = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
SPACES = dict.fromkeys(map(ord, "        "), " ")


def clean_chars(s: str) -> str:
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return s.translate(DROP).translate(SPACES)


# ---------------------------------------------------------------- 2. segments
def segments_of(words: list[Box]) -> list[Box]:
    """Group words left to right into segments: same baseline, gap under ~1 line height."""
    words = [w for w in words if clean_chars(w.text).strip()]
    # vertical (rotated) words: taller than wide. Kept apart as their own segments.
    rotated = [w for w in words if len(w.text) >= 3 and (w.x1 - w.x0) < 0.45 * w.h]
    words = [w for w in words if w not in rotated]
    segs: list[Box] = [Box(w.x0, w.y0, w.x1, w.y1, "", [w]) for w in rotated]
    for w in sorted(words, key=lambda w: (w.x0, w.y0)):
        best = None
        best_gap = None
        for s in segs:
            gap = w.x0 - s.x1
            if s.words[0] in rotated or not (-0.5 < gap < 1.0 * min(s.words[-1].h, w.h)):
                continue
            base, last = s.words[0], s.words[-1]
            ok = False
            for ref in (base, last):
                ov = min(ref.y1, w.y1) - max(ref.y0, w.y0)
                if ov >= 0.5 * min(ref.h, w.h):
                    ok = True
            if ok and (best_gap is None or gap < best_gap):
                best, best_gap = s, gap
        if best:
            best.words.append(w)
            best.x1 = max(best.x1, w.x1)
            best.y0 = min(best.y0, w.y0)
            best.y1 = max(best.y1, w.y1)
        else:
            segs.append(Box(w.x0, w.y0, w.x1, w.y1, "", [w]))
    for s in segs:
        parts = []
        prev = None
        for w in s.words:
            if prev is not None and w.x0 - prev.x1 > 0.12 * min(prev.h, w.h):
                parts.append(" ")
            parts.append(w.text)
            prev = w
        s.text = clean_chars("".join(parts)).strip()
    return [s for s in segs if s.text]


# ---------------------------------------------------------------- 3. clutter
URL_RE = re.compile(r"(https?://|www\.)\S+|\b\S+\.(com|org|net|no|uk|dk)/\S*", re.I)
DATE_RE = re.compile(r"\b(\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2})\b(,?\s*\d{1,2}[:.]\d{2})?")
PAGE_RE = re.compile(r"^(page\s*)?\d{1,3}\s*(/|of|av|af|von|de)\s*\d{1,3}$|^-?\s*\d{1,3}\s*-?$", re.I)
STAMP_RE = re.compile(r"powered by tcpdf|^sku[:\s]", re.I)


def norm_key(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", s.lower())).strip()


def strip_clutter(pages: list[Page]) -> None:
    margin = 0.075   # top/bottom share of page treated as header/footer zone
    counts = Counter()
    for p in pages:
        for k in {norm_key(s.text) for s in p.segments if in_margin(s, p, 0.12)}:
            if len(re.findall(r"[^\W\d_]", k)) >= 3:      # page numbers alone are handled by PAGE_RE
                counts[k] += 1
    repeat_min = max(3, len(pages) // 2 + 1) if len(pages) >= 3 else 99
    for p in pages:
        keep = []
        for s in p.segments:
            t = s.text
            why = None
            if STAMP_RE.search(t):
                why = "stamp"
            elif in_margin(s, p, margin) and len(t) <= 90 and (URL_RE.search(t) or DATE_RE.search(t) or (
                    PAGE_RE.match(t) and alone_on_row(s, p.segments))):
                why = "browser header/footer"
            elif in_margin(s, p, 0.12) and counts[norm_key(t)] >= repeat_min:
                why = "repeats on %d pages" % counts[norm_key(t)]
            if why:
                p.removed.append((why, t))
            else:
                keep.append(s)
        p.segments = keep


def alone_on_row(s: Box, segs: list[Box]) -> bool:
    return not any(t is not s and min(t.y1, s.y1) - max(t.y0, s.y0) > 0.3 * min(t.h, s.h) for t in segs)


def in_margin(s: Box, p: Page, frac: float) -> bool:
    return s.y1 < p.height * frac or s.y0 > p.height * (1 - frac)


# ---------------------------------------------------------------- 4. reading order
def bands_for(segs: list[Box], x: float):
    """Cut the region at every segment crossing x. Returns list of (kind, payload) top to bottom:
    ("row", seg) for a crossing segment, ("band", [segs]) for the segments between two crossings."""
    crossing = sorted([s for s in segs if s.x0 < x - 0.5 and s.x1 > x + 0.5], key=lambda s: s.cy)
    cuts = [s.cy for s in crossing]
    bands: list[list[Box]] = [[] for _ in range(len(cuts) + 1)]
    for s in segs:
        if s in crossing:
            continue
        bands[sum(1 for c in cuts if s.cy > c)].append(s)
    out = []
    for i, b in enumerate(bands):
        if b:
            out.append(("band", b))
        if i < len(crossing):
            out.append(("row", crossing[i]))
    return out


def text_like(side: list[Box]) -> bool:
    """Running text: much of the side's text sits in segments spanning a good part of its width.
    Table cells and chart numbers are narrow, so a half-table fails this."""
    ext = max(s.x1 for s in side) - min(s.x0 for s in side)
    total = sum(len(s.text) for s in side)
    wide = sum(len(s.text) for s in side if s.x1 - s.x0 >= 0.4 * ext)
    return total > 0 and wide >= 0.4 * total


def aligned_share(a: list[Box], b: list[Box]) -> float:
    """Share of the text rows (baselines) in a that also carry text in b."""
    rows = rows_of(a)
    n = sum(1 for r in rows if any(abs(r[0].cy - t.cy) < 0.3 * min(r[0].h, t.h) for t in b))
    return n / len(rows)


def is_column_band(band: list[Box], x: float, region_w: float) -> bool:
    left = [s for s in band if s.x1 <= x + 0.5]
    right = [s for s in band if s.x0 >= x - 0.5]
    if len(left) < 2 or len(right) < 2:
        return False
    for side in (left, right):
        if max(s.x1 for s in side) - min(s.x0 for s in side) < max(0.2 * region_w, 60.0):
            return False
    ly = (min(s.y0 for s in left), max(s.y1 for s in left))
    ry = (min(s.y0 for s in right), max(s.y1 for s in right))
    if min(ly[1], ry[1]) - max(ly[0], ry[0]) <= 0:      # one above the other, not side by side
        return False
    tl, tr = text_like(left), text_like(right)
    if tl and tr:
        # short entries that pair up row by row are a table (term | meaning), not two columns
        short = all(sorted(len(s.text) for s in side)[len(side) // 2] <= 20 for side in (left, right))
        return not (short and aligned_share(left, right) >= 0.6 and aligned_share(right, left) >= 0.6)
    if tl or tr:
        # text beside a table or figure labels: columns unless the rows line up like one table
        narrow = right if tl else left
        wide = left if tl else right
        return aligned_share(narrow, wide) < 0.5
    return False


def find_gutter(segs: list[Box]):
    if len(segs) < 4:
        return None
    x0 = min(s.x0 for s in segs)
    x1 = max(s.x1 for s in segs)
    w = x1 - x0
    scores = []
    x = x0 + 0.25 * w
    while x <= x1 - 0.25 * w:
        if any(s.x0 < x + 2 and s.x1 > x - 2 and not (s.x0 < x - 0.5 and s.x1 > x + 0.5) for s in segs):
            scores.append((x, 0))   # an edge within 2pt: not clear whitespace
        else:
            sc = sum(len(p) for k, p in bands_for(segs, x) if k == "band" and is_column_band(p, x, w))
            scores.append((x, sc))
        x += 1.0
    best = max((sc for _, sc in scores), default=0)
    if best < 4:
        return None
    # centre of the longest run of x positions that reach the best score
    runs, cur = [], []
    for xx, sc in scores:
        if sc == best:
            cur.append(xx)
        elif cur:
            runs.append(cur); cur = []
    if cur:
        runs.append(cur)
    run = max(runs, key=len)
    return run[len(run) // 2]


def split_at_gaps(segs: list[Box], factor: float = 2.5) -> list[list[Box]]:
    """Cut where no text at all lies across the region for a height of at least factor x line height."""
    hs = sorted(s.h for s in segs)
    min_gap = factor * hs[len(hs) // 2]
    blocks: list[list[Box]] = []
    bottom = None
    for s in sorted(segs, key=lambda s: s.y0):
        if bottom is not None and s.y0 - bottom >= min_gap:
            blocks.append([])
        if not blocks:
            blocks.append([])
        blocks[-1].append(s)
        bottom = s.y1 if bottom is None else max(bottom, s.y1)
    return blocks


def order(segs: list[Box], depth: int = 0) -> list[list[Box]]:
    """Return rows (lists of segments on one baseline) in reading order."""
    if not segs:
        return []
    g = find_gutter(segs) if depth < 12 else None
    if g is None:
        blocks = split_at_gaps(segs) if depth < 12 else [segs]
        if len(blocks) > 1:
            return [row for b in blocks for row in order(b, depth + 1)]
        return rows_of(segs)
    w = max(s.x1 for s in segs) - min(s.x0 for s in segs)
    out: list[list[Box]] = []
    other: list[Box] = []          # full-width rows and non-column bands, gathered until the next column band

    def flush():
        if other:
            out.extend(order(list(other), depth + 1) if len(other) < len(segs) else rows_of(other))
            other.clear()

    for kind, p in bands_for(segs, g):
        if kind == "band" and is_column_band(p, g, w):
            flush()
            out.extend(order([s for s in p if s.x1 <= g + 0.5], depth + 1))
            out.extend(order([s for s in p if s.x0 >= g - 0.5], depth + 1))
        elif kind == "band":
            other.extend(p)
        else:
            other.append(p)
    flush()
    return out


def rows_of(segs: list[Box]) -> list[list[Box]]:
    rows: list[list[Box]] = []
    for s in sorted(segs, key=lambda s: (s.cy, s.x0)):
        if rows:
            r = rows[-1]
            ry0 = min(t.y0 for t in r)
            ry1 = max(t.y1 for t in r)
            rc = (ry0 + ry1) / 2
            if abs(s.cy - rc) < 0.4 * min(s.h, ry1 - ry0):
                r.append(s)
                continue
        rows.append([s])
    for r in rows:
        r.sort(key=lambda s: s.x0)
    return rows


# ---------------------------------------------------------------- 4b. tables
def group_tables(segs: list[Box], max_cell: int = 25) -> list[Box]:
    """Rows with 3+ short segments close together, stacked 2+ high, become one atomic table box,
    so that column finding never splits a table and the table is read row by row."""
    runs = []   # (x0, x1, y0, y1, cells) per row run
    for row in rows_of(segs):
        cur: list[Box] = []
        for s in row + [None]:
            if s is not None and len(s.text) <= max_cell and (not cur or s.x0 - cur[-1].x1 < 120):
                cur.append(s)
                continue
            if len(cur) >= 3:
                runs.append(cur)
            cur = [s] if s is not None and len(s.text) <= max_cell else []
    tables: list[list[list[Box]]] = []
    for r in runs:
        x0, x1 = min(s.x0 for s in r), max(s.x1 for s in r)
        y0 = min(s.y0 for s in r)
        h = max(s.h for s in r)
        for t in tables:
            last = t[-1]
            lx0, lx1 = min(s.x0 for s in last), max(s.x1 for s in last)
            ov = min(x1, lx1) - max(x0, lx0)
            if 0 <= y0 - max(s.y1 for s in last) < 2.5 * h and ov > 0.5 * min(x1 - x0, lx1 - lx0):
                t.append(r)
                break
        else:
            tables.append([r])
    used = set()
    out: list[Box] = []
    for t in tables:
        if len(t) < 2:
            continue
        cells = [s for r in t for s in r]
        # header lines just above (2+ short segments inside the table's width) belong to it
        x0, x1 = min(s.x0 for s in cells), max(s.x1 for s in cells)
        for _ in range(3):
            top = min(s.y0 for s in cells)
            above = [s for s in segs if id(s) not in used and s not in cells and len(s.text) <= max_cell
                     and s.x0 >= x0 - 5 and s.x1 <= x1 + 5 and 0 <= top - s.y1 < 1.5 * s.h]
            if len(above) < 2:
                break
            cells += above
        used.update(id(s) for s in cells)
        out.append(Box(min(s.x0 for s in cells), min(s.y0 for s in cells), max(s.x1 for s in cells),
                       max(s.y1 for s in cells), "[table]", [], cells))
    return [s for s in segs if id(s) not in used] + out


def page_lines(segs: list[Box]) -> list[str]:
    lines = []
    for row in order(group_tables(segs)):
        plain = [s for s in row if not s.cells]
        if plain:
            lines.append(" ".join(s.text for s in plain))
        for t in (s for s in row if s.cells):
            lines += [" ".join(c.text for c in r) for r in rows_of(t.cells)]
    return join_lines(lines)


# ---------------------------------------------------------------- 6. joining
HYPHEN_END = re.compile(r"[\d½¼¾]\s*[-–]\s*$")
DIGIT_START = re.compile(r"^\s*[\d½¼¾]")


def join_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        if out and HYPHEN_END.search(out[-1]) and DIGIT_START.match(ln):
            out[-1] = out[-1].rstrip() + ln.lstrip()
        else:
            out.append(ln)
    return out


# ---------------------------------------------------------------- 8. coverage
def ink_stats(pdf: str, p: Page, px_w: int = 160) -> tuple[float, float]:
    """Share of the page that is not background, and the share of that lying outside word boxes."""
    from PIL import Image, ImageChops, ImageDraw
    png = subprocess.run(["pdftoppm", "-scale-to-x", str(px_w), "-scale-to-y", "-1", "-gray", "-png",
                          "-f", str(p.number), "-l", str(p.number), pdf],
                         capture_output=True, check=True, timeout=60).stdout
    im = Image.open(io.BytesIO(png)).convert("L")
    w, h = im.size
    hist = im.histogram()
    bg = max(range(256), key=lambda v: hist[v])          # most common grey = background
    ink = im.point(lambda v: 255 if abs(v - bg) > 40 else 0)
    mask = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(mask)
    sx, sy = w / p.width, h / p.height
    for b in p.words:
        d.rectangle([b.x0 * sx - 1, b.y0 * sy - 1, b.x1 * sx + 1, b.y1 * sy + 1], fill=0)
    outside = ImageChops.multiply(ink, mask)
    n = float(w * h)
    return ink.histogram()[255] / n, outside.histogram()[255] / n


def classify(p: Page) -> str:
    if p.chars < 40 and p.ink < 0.01:
        return "blank"
    if p.chars < 150:
        return "no-text: needs picture reading"
    if p.ink_outside_text > 0.25 and p.chars < 600:
        return "mostly image: check with picture"
    return "text"


# ---------------------------------------------------------------- links (pypdf, BSD)
def links(pdf: str, pages: list[Page]) -> list[dict]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    r = PdfReader(pdf)
    found = []
    for i, pg in enumerate(r.pages):
        ph = float(pg.mediabox.top)
        for a in pg.get("/Annots") or []:
            a = a.get_object()
            if a.get("/Subtype") != "/Link":
                continue
            act = a.get("/A")
            act = act.get_object() if act else None
            uri = act.get("/URI") if act else None
            if not uri:
                continue
            x0, y0, x1, y1 = [float(v) for v in a["/Rect"]]
            # PDF space is bottom-up; poppler boxes are top-down
            ty0, ty1 = ph - max(y0, y1), ph - min(y0, y1)
            anchor = ""
            match = [p for p in pages if p.number == i + 1]
            if match:
                ws = [w for w in match[0].words
                      if min(x0, x1) - 2 <= (w.x0 + w.x1) / 2 <= max(x0, x1) + 2 and ty0 - 2 <= w.cy <= ty1 + 2]
                anchor = clean_chars(" ".join(w.text for w in ws))
            found.append({"page": i + 1, "url": str(uri), "anchor": anchor[:80]})
    return found


# ---------------------------------------------------------------- driver
def extract(pdf: str, first=None, last=None, coverage=True) -> list[Page]:
    pages = read_words(pdf, first, last)
    for p in pages:
        p.segments = segments_of(p.words)
    strip_clutter(pages)
    for p in pages:
        p.lines = page_lines(p.segments)
        p.chars = sum(len(re.sub(r"\s", "", clean_chars(w.text))) for w in p.words)
        if coverage:
            p.ink, p.ink_outside_text = ink_stats(pdf, p)
        p.status = classify(p)
    return pages


def main():
    args = sys.argv[1:]
    pdf = args[0]
    first = last = None
    if "--pages" in args:
        a, _, b = args[args.index("--pages") + 1].partition("-")
        first, last = int(a), int(b or a)
    t = time.perf_counter()
    pages = extract(pdf, first, last, coverage="--nocov" not in args)
    dt = time.perf_counter() - t
    if "--json" in args:
        print(json.dumps({"seconds": dt, "pages": [
            {"page": p.number, "status": p.status, "chars": p.chars, "ink": round(p.ink, 3),
             "ink_outside_text": round(p.ink_outside_text, 3), "removed": p.removed, "lines": p.lines}
            for p in pages], "links": links(pdf, pages)}, ensure_ascii=False, indent=1))
        return
    for p in pages:
        print(f"===== page {p.number}  [{p.status}; chars={p.chars} ink={p.ink:.3f} "
              f"non-text ink={p.ink_outside_text:.3f}]")
        for why, t in p.removed:
            print(f"  (removed, {why}: {t[:60]})")
        print("\n".join(p.lines))
    for l in links(pdf, pages):
        print(f"LINK p{l['page']}: {l['url']}  [{l['anchor']}]")
    print(f"# {dt:.2f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
