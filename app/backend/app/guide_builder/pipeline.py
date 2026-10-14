"""Build a guide (format 0.2) from a pattern PDF.

Stages (each reports progress):
  read      code: text in reading order, clutter removed, which pages need picture reading
  pictures  AI: transcribe pages without usable text, one page per call, in parallel
  outline   AI: one call for options, materials, techniques, charts and the list of sections
  sections  AI: one call per section, in parallel; steps come back as exact quotes
  checks    code: find every quote in the pattern, copy the numbers from the pattern text ("AI marks, code copies"),
            build the full guide, raise doubts for anything that does not trace back to the pattern
  repair    AI: re-ask only the sections whose quotes could not be found
"""
from __future__ import annotations

import datetime as dt
import difflib
import io
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import ai, prompts, reader, schemas, sizes
from .progress import Event, Reporter, silent

PIPELINE = "guide_builder 0.1"
IMAGE_DPI = 90
MAX_SECTION_IMAGES = 4
HEARTBEAT_SECONDS = 3.0   # while a model call is running, repeat the latest event this often, with the elapsed time


# ---------------------------------------------------------------- result
@dataclass
class BuildResult:
    guide: dict
    report: dict = field(default_factory=dict)


@dataclass
class _Usage:
    calls: int = 0
    prompt: int = 0
    completion: int = 0
    reasoning: int = 0
    cost: float = 0.0
    modes: dict = field(default_factory=dict)

    def add(self, ans: ai.Answer) -> None:
        u = ans.usage or {}
        self.calls += 1
        self.prompt += int(u.get("prompt_tokens") or 0)
        self.completion += int(u.get("completion_tokens") or 0)
        self.reasoning += int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        self.cost += ans.cost
        self.modes[ans.mode] = self.modes.get(ans.mode, 0) + 1


# ---------------------------------------------------------------- text matching ("AI marks, code copies")
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = {ord("’"): "'", ord("‘"): "'", ord("“"): '"', ord("”"): '"', ord("″"): '"'}


def _norm_char(c: str) -> str:
    c = unicodedata.normalize("NFKC", c)
    return c.translate(_DASHES).translate(_QUOTES).lower()


def _normalise(text: str) -> tuple[str, list[int]]:
    """Normalised text plus, for each normalised character, its index in the original. Whitespace runs become one
    space; dashes, quotes and ligatures are unified; letters lowered."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, c in enumerate(text):
        if c.isspace() or c in "​­⁠":
            if c in "​­⁠":
                continue
            if not prev_space and out:
                out.append(" ")
                idx.append(i)
            prev_space = True
            continue
        prev_space = False
        for nc in _norm_char(c):
            out.append(nc)
            idx.append(i)
    return "".join(out), idx


def locate(quote: str | None, text: str, *, min_ratio: float = 0.85) -> tuple[int, int, float] | None:
    """Find a quote in the source text. Returns (start, end, score) in original offsets, or None.
    score is 1.0 for an exact (normalised) match, otherwise the similarity of the best window."""
    if not quote or not text:
        return None
    nq, _ = _normalise(quote.strip())
    nt, idx = _normalise(text)
    if not nq:
        return None
    pos = nt.find(nq)
    if pos >= 0:
        return idx[pos], idx[pos + len(nq) - 1] + 1, 1.0
    if len(nq) < 12:
        return None
    sm = difflib.SequenceMatcher(None, nt, nq, autojunk=False)
    best = None
    for block in sm.get_matching_blocks():
        if block.size < 8:
            continue
        start = max(0, block.a - block.b)
        window = nt[start:start + len(nq) + 20]
        ratio = difflib.SequenceMatcher(None, window[: len(nq)], nq, autojunk=False).ratio()
        if best is None or ratio > best[2]:
            best = (start, min(len(nt), start + len(nq)), ratio)
    if best and best[2] >= min_ratio:
        s, e, r = best
        return idx[s], idx[e - 1] + 1, round(r, 3)
    return None


# ---------------------------------------------------------------- helpers
def _slug(s: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()).strip("-") or "x"
    base = base[:24]
    out, n = base, 2
    while out in taken:
        out, n = f"{base}-{n}", n + 1
    taken.add(out)
    return out


def _page_images(pdf: str, dpi: int = IMAGE_DPI) -> dict[int, bytes]:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-jpeg", "-jpegopt", "quality=80", "-r", str(dpi), pdf, f"{tmp}/p"],
                       check=True, capture_output=True, timeout=300)
        out = {}
        for f in Path(tmp).glob("p-*.jpg"):
            out[int(f.stem.split("-")[-1])] = f.read_bytes()
        return out


def _publisher(text: str) -> str | None:
    t = text.lower()
    if "garnstudio" in t or "drops design" in t:
        return "drops"
    if "hobbii" in t:
        return "hobbii"
    return None


def _source(page, quote: str, picture: bool) -> dict:
    return {"page": page, "quote": (quote or "")[:300], "from_picture": bool(picture)}


def _not_given(text: str = "") -> dict:
    return {"text": text, "unit": None, "all": None, "by_size": None, "by_choice": None, "from_picture": False, "alt": None}


# ---------------------------------------------------------------- builder
class Builder:
    def __init__(self, pdf: str, client: ai.Client, report: Reporter = silent, workers: int = 6):
        self.pdf = str(pdf)
        self.client = client
        self.report = report
        self.workers = workers
        self.usage = _Usage()
        self.timings: dict[str, float] = {}
        self.errors: list[str] = []
        self.code_doubts: list[dict] = []
        self._last: Event | None = None
        self._lock = threading.Lock()
        self._started = time.time()

    def _emit(self, stage, message, done=0, total=0, **detail):
        event = Event(stage, message, done, total, detail)
        with self._lock:
            self._last = event
        self._send(event)

    def _send(self, event: Event) -> None:
        try:
            self.report(event)
        except Exception:  # a broken progress listener must never stop the build
            pass

    def _heartbeat(self, stop: threading.Event) -> None:
        """Re-send the latest event with the elapsed seconds, so a page that comes back from sleep sees it move."""
        while not stop.wait(HEARTBEAT_SECONDS):
            with self._lock:
                last = self._last
            if last is None or last.stage == "done":
                continue
            self._send(Event(last.stage, last.message, last.done, last.total,
                             {**last.detail, "heartbeat": True, "elapsed": round(time.time() - self._started)}))

    # ------------------------------------------------ stages
    def run(self) -> BuildResult:
        stop = threading.Event()
        beat = threading.Thread(target=self._heartbeat, args=(stop,), daemon=True)
        beat.start()
        try:
            return self._run()
        finally:
            stop.set()
            beat.join(timeout=HEARTBEAT_SECONDS + 1)

    def _run(self) -> BuildResult:
        t0 = time.time()
        self._emit("read", "Reading the pattern")
        doc = reader.read(self.pdf)
        self.images = _page_images(self.pdf)
        self.pages = {p.number: p.text for p in doc.pages}
        self.picture_pages: set[int] = set()
        self.links = doc.links
        self.timings["read"] = round(time.time() - t0, 1)

        self._pictures([p.number for p in doc.pages if p.needs_picture])
        self.full_text = "\n\n".join(f"=== Page {n} ===\n{self.pages[n]}" for n in sorted(self.pages))
        self.publisher = _publisher(self.full_text)

        t = time.time()
        self._emit("outline", "Finding sizes, yarn and sections")
        self.outline = self._outline()
        self.timings["outline"] = round(time.time() - t, 1)

        t = time.time()
        sections = self._split_sections()
        self.section_answers = self._sections(sections)
        self.timings["sections"] = round(time.time() - t, 1)

        t = time.time()
        self._emit("checks", "Checking every number against the pattern")
        guide = self._assemble(sections)
        self.timings["checks"] = round(time.time() - t, 1)

        weak = [i for i, s in enumerate(guide["sections"]) if self._unlocated_share(s) > 0.2]
        if weak:
            t = time.time()
            self._emit("repair", f"Taking a second look at {len(weak)} section(s)", 0, len(weak))
            self._repair(sections, weak)
            guide = self._assemble(sections)
            self.timings["repair"] = round(time.time() - t, 1)

        problems = schemas.problems(guide)
        self._emit("done", "Ready to check")
        report = {
            "pipeline": PIPELINE, "model": self.client.cfg.model, "seconds": round(time.time() - t0, 1),
            "timings": self.timings, "calls": self.usage.calls, "prompt_tokens": self.usage.prompt,
            "completion_tokens": self.usage.completion, "reasoning_tokens": self.usage.reasoning,
            "cost": round(self.usage.cost, 5), "modes": self.usage.modes, "errors": self.errors,
            "picture_pages": sorted(self.picture_pages), "validation_problems": problems[:50],
        }
        return BuildResult(guide, report)

    def _pictures(self, numbers: list[int]) -> None:
        if not numbers:
            return
        t = time.time()
        total = len(numbers)
        done = 0
        self._emit("pictures", f"Reading pages that are pictures (0 of {total})", 0, total)

        def one(n):
            ans = self.client.text(prompts.PICTURE, [ai.text_part(f"Page {n} of the pattern."), ai.image_part(self.images[n])])
            return n, ans

        with ThreadPoolExecutor(self.workers) as pool:
            for fut in [pool.submit(one, n) for n in numbers]:
                try:
                    n, ans = fut.result()
                except ai.AIError as exc:
                    self.errors.append(f"picture page: {exc}")
                    continue
                finally:
                    done += 1
                    self._emit("pictures", f"Reading pages that are pictures ({done} of {total})", done, total)
                self.usage.add(ans)
                text = ans.data["text"].strip()
                if text and text != "(no pattern content)":
                    existing = self.pages.get(n, "").strip()
                    self.pages[n] = (existing + "\n" if len(existing) > 40 else "") + text
                    self.picture_pages.add(n)
        self.timings["pictures"] = round(time.time() - t, 1)

    def _outline(self) -> dict:
        hint = prompts.PUBLISHER_HINTS.get(self.publisher or "", "")
        content = [ai.text_part(f"{hint}\nPattern text, page by page:\n{self.full_text}")]
        for n in sorted(self.images):
            content += [ai.text_part(f"=== Page {n} image ==="), ai.image_part(self.images[n])]
        ans = self.client.json(prompts.OUTLINE, content, schemas.AI_OUTLINE, "pattern_outline")
        self.usage.add(ans)
        return ans.data

    def _split_sections(self) -> list[dict]:
        """Cut the pattern text into the outline's sections, using each section's start quote."""
        out = []
        starts = []
        for sec in self.outline.get("sections", []):
            loc = locate(sec.get("start_quote"), self.full_text, min_ratio=0.8)
            starts.append(loc[0] if loc else None)
        ordered = sorted([(s, i) for i, s in enumerate(starts) if s is not None])
        bounds = {}
        for k, (s, i) in enumerate(ordered):
            end = ordered[k + 1][0] if k + 1 < len(ordered) else len(self.full_text)
            bounds[i] = (s, end)
        for i, sec in enumerate(self.outline.get("sections", [])):
            if i in bounds:
                s, e = bounds[i]
                text = self.full_text[s:e]
            else:  # fall back to the section's pages
                first = sec.get("first_page") or 1
                last = sec.get("last_page") or first
                text = "\n\n".join(f"=== Page {n} ===\n{self.pages.get(n, '')}" for n in range(first, last + 1))
                self.errors.append(f"section start not found: {sec.get('name')}")
            before = re.findall(r"=== Page (\d+) ===", self.full_text[: bounds[i][0]]) if i in bounds else []
            pages = sorted({int(m) for m in before[-1:]} | {int(m) for m in re.findall(r"=== Page (\d+) ===", text)})
            if not pages:
                pages = [sec.get("first_page") or 1]
            out.append({"outline": sec, "text": text, "pages": pages})
        return out

    def _section_content(self, sec: dict, feedback: str = "") -> list[dict]:
        o = self.outline
        context = (f"Pattern: {o.get('title')}. Sizes in order: {', '.join(o.get('sizes', []))}. "
                   f"Size notation: {o.get('size_notation')}. "
                   f"Choices: {'; '.join(c['name'] + ': ' + ', '.join(c['values']) for c in o.get('choices', [])) or 'none'}. "
                   f"Techniques: {', '.join(t['name'] for t in o.get('techniques', [])) or 'none'}. "
                   f"Charts: {', '.join(c['name'] for c in o.get('charts', [])) or 'none'}.\n"
                   f"{prompts.PUBLISHER_HINTS.get(self.publisher or '', '')}\n"
                   f"Section: {sec['outline']['name']}"
                   + (f" (worked as: {', '.join(sec['outline'].get('instances') or [])})" if sec['outline'].get('instances') else "")
                   + f"\n{feedback}\nSection text:\n{sec['text']}")
        content = [ai.text_part(context)]
        for n in sec["pages"][:MAX_SECTION_IMAGES]:
            if n in self.images:
                content += [ai.text_part(f"=== Page {n} image ==="), ai.image_part(self.images[n])]
        return content

    def _sections(self, sections: list[dict], feedback: dict[int, str] | None = None) -> dict[int, dict]:
        total = len(sections)
        results: dict[int, dict] = {}
        done = 0
        self._emit("sections", f"Writing the steps (0 of {total} sections)", 0, total)

        def one(i):
            sec = sections[i]
            ans = self.client.json(prompts.SECTION, self._section_content(sec, (feedback or {}).get(i, "")),
                                   schemas.AI_SECTION, "pattern_section")
            return i, ans

        indexes = list(feedback) if feedback else list(range(total))
        with ThreadPoolExecutor(self.workers) as pool:
            futures = [pool.submit(one, i) for i in indexes]
            for fut in futures:
                try:
                    i, ans = fut.result()
                    self.usage.add(ans)
                    results[i] = ans.data
                except ai.AIError as exc:
                    self.errors.append(f"section: {exc}")
                done += 1
                name = sections[indexes[done - 1]]["outline"]["name"]
                self._emit("sections", f"Writing the steps: {name} ({done} of {len(indexes)})", done, len(indexes),
                           section=name)
        return results

    def _repair(self, sections: list[dict], weak: list[int]) -> None:
        feedback = {}
        for i in weak:
            missing = [st.get("quote", "")[:120] for st in (self.section_answers.get(i) or {}).get("steps", [])
                       if not locate(st.get("quote"), sections[i]["text"])]
            feedback[i] = ("Last time some quotes could not be found in the section text. Copy each instruction "
                           "exactly, character for character. Not found: " + " | ".join(missing[:8]))
        redone = self._sections(sections, feedback)
        for i, data in redone.items():
            old = self.section_answers.get(i) or {"steps": []}
            found_new = sum(1 for st in data.get("steps", []) if locate(st.get("quote"), sections[i]["text"]))
            found_old = sum(1 for st in old.get("steps", []) if locate(st.get("quote"), sections[i]["text"]))
            if found_new >= found_old:
                self.section_answers[i] = data

    @staticmethod
    def _unlocated_share(section: dict) -> float:
        steps = section["steps"]
        if not steps:
            return 1.0
        return sum(1 for s in steps if s["confidence"] == "low") / len(steps)

    # ------------------------------------------------ assembly
    def _assemble(self, sections: list[dict]) -> dict:
        o = self.outline
        self.code_doubts = []
        labels = [str(x) for x in o.get("sizes") or ["One size"]]
        n = len(labels)
        taken: set[str] = set()
        size_ids = [_slug(lbl, taken) for lbl in labels]
        choices, choice_ids = [], {}
        for c in (o.get("choices") or [])[:2]:
            cid = _slug(c["name"], taken)
            vals = []
            for v in c["values"]:
                vid = _slug(v, taken)
                choice_ids[v] = vid
                vals.append({"id": vid, "label": v})
            choices.append({"id": cid, "name": c["name"], "values": vals})
        notation = o.get("size_notation") or ""
        clabels = list(choice_ids) or None

        def qty(quote, unit=None, picture=False, where=None):
            if not quote:
                return None
            loc = locate(quote, where or self.full_text)
            src = (where or self.full_text)[loc[0]:loc[1]] if loc else quote
            sv = sizes.quantity(src, n, notation=notation, prefer_unit=unit, size_labels=labels,
                                choice_labels=clabels, choice_ids=choice_ids, from_picture=picture)
            if sv is not None and not loc:
                self._doubt("other", f"The value \"{quote[:60]}\" could not be found in the pattern text; check it.",
                            source=None)
            return sv

        def page_of(offset: int) -> int | None:
            pages = re.findall(r"=== Page (\d+) ===", self.full_text[:offset])
            return int(pages[-1]) if pages else None

        # front matter
        size_guide_rows = []
        for row in (o.get("size_guide") or {}).get("rows", []):
            loc = locate(row["quote"], self.full_text)
            src = self.full_text[loc[0]:loc[1]] if loc else row["quote"]
            runs = sizes.find_runs(src, n, notation=notation, size_labels=labels)
            pic = bool(row.get("from_picture")) or (row.get("page") in self.picture_pages)
            value = sizes.to_sized_value(runs[0] if runs else None, n, text=src, from_picture=pic) if runs else \
                sizes.quantity(src, n, notation=notation, size_labels=labels, from_picture=pic) or _not_given(src)
            self._check_runs(runs, f"size guide: {row['name']}")
            size_guide_rows.append({"name": row["name"], "value": value, "source": _source(row.get("page"), src, pic)})
        sg = o.get("size_guide") or {}

        yarns = []
        for k, y in enumerate(o.get("yarns") or []):
            amount = qty(y.get("amount_quote"), "g", bool(y.get("from_picture"))) or _not_given(y.get("amount_quote") or "")
            yarns.append({
                "id": f"y{k + 1}", "name": y["name"], "weight": y.get("weight"), "fibre": y.get("fibre"),
                "ball": y.get("ball"), "colour": y.get("colour"), "strand_group": y.get("strand_group"),
                "alternative_group": y.get("alternative_group"), "alternatives_text": y.get("alternatives_text"),
                "amount": amount,
                "applies_to": {"sizes": None, "choices": [choice_ids[y["choice_value"]]], "except": []}
                if y.get("choice_value") in choice_ids else None,
                "source": _source(y.get("page"), y.get("amount_quote") or y["name"], bool(y.get("from_picture"))),
            })
        needles = [self._needle(k, x, choice_ids, n, notation, labels) for k, x in enumerate(o.get("needles") or [])]
        gauge = [self._gauge(x, choice_ids) for x in o.get("gauge") or []]
        notions = [{"text": x["text"], "amount": None, "applies_to": None, "source": _source(x.get("page"), x["text"], False)}
                   for x in o.get("notions") or []]
        abbreviations = [{"abbr": a["abbr"], "meaning": a["meaning"], "defined_in_pattern": bool(a["defined"]),
                          "source": _source(None, a["abbr"], False)} for a in o.get("abbreviations") or []]
        tech_taken: set[str] = set()
        techniques, tech_by_name = [], {}
        for t in o.get("techniques") or []:
            tid = _slug(t["name"], tech_taken)
            loc = locate(t["quote"], self.full_text)
            text = self.full_text[loc[0]:loc[1]] if loc else t["quote"]
            techniques.append({"id": tid, "name": t["name"], "text": text, "slots": [],
                               "source": _source(t.get("page"), t["quote"][:120], t.get("page") in self.picture_pages)})
            tech_by_name[t["name"].strip().lower()] = tid
        chart_taken: set[str] = set()
        charts, chart_by_name = [], {}
        for c in o.get("charts") or []:
            cid = _slug(c["name"], chart_taken)
            charts.append({"id": cid, "name": c["name"], "page": c.get("page"), "kind": c["kind"],
                           "applies_to": self._applies_from_note(c.get("applies_text"), labels, size_ids),
                           "width": None, "height": None, "start_points": [],
                           "written_alternative": bool(c.get("written_alternative")), "notes": c.get("applies_text"),
                           "source": _source(c.get("page"), c["name"], True)})
            chart_by_name[c["name"].strip().lower()] = cid

        # sections and steps
        sec_taken: set[str] = set()
        out_sections, reminders = [], []
        sec_ids = [_slug(s["outline"]["name"], sec_taken) for s in sections]
        name_to_sec = {s["outline"]["name"].strip().lower(): sid for s, sid in zip(sections, sec_ids)}
        for i, sec in enumerate(sections):
            sid = sec_ids[i]
            data = self.section_answers.get(i) or {"steps": [], "reminders": [], "doubts": []}
            if i not in self.section_answers:
                self._doubt("missing", f"The steps for \"{sec['outline']['name']}\" could not be built. Add them by hand "
                                       "or rebuild the guide.", source=None)
            steps = []
            for k, st in enumerate(data.get("steps", [])):
                steps.append(self._step(sid, k, st, sec, n, labels, size_ids, notation, clabels, choice_ids,
                                        tech_by_name, chart_by_name))
            if sec["outline"].get("based_on_section") and steps:
                base = name_to_sec.get(sec["outline"]["based_on_section"].strip().lower())
                if base:
                    steps[0]["based_on"] = {"section_id": base, "from_text": None, "to_text": None, "changes": None}
            first_loc = locate(sec["outline"].get("start_quote"), self.full_text)
            out_sections.append({
                "id": sid, "name": sec["outline"]["name"], "instances": sec["outline"].get("instances") or [],
                "mirrored": bool(sec["outline"].get("mirrored")), "implied": bool(sec["outline"].get("implied")),
                "steps": steps,
                "source": _source(page_of(first_loc[0]) if first_loc else sec["outline"].get("first_page"),
                                  sec["outline"].get("start_quote") or sec["outline"]["name"],
                                  bool(set(sec["pages"]) & self.picture_pages)),
            })
            for r_k, r in enumerate(data.get("reminders", [])):
                if not steps:
                    continue
                every = qty(r.get("quote"), where=sec["text"])
                reminders.append({
                    "id": f"{sid}-reminder-{r_k + 1}", "text": r["text"],
                    "schedule": None if every is None else {
                        "action": r["text"], "slots": [], "every": every, "every_unit": None, "on_rows": None,
                        "times": None, "first_at": None, "until": None, "checkpoint": None,
                        "source": _source(steps[0]["source"]["page"], r.get("quote") or r["text"], False)},
                    "from_step": steps[0]["id"], "until_step": None if r.get("until") else steps[-1]["id"],
                    "source": _source(steps[0]["source"]["page"], r.get("quote") or r["text"], False),
                })
            for d in data.get("doubts", []):
                self._doubt(d["kind"], d["message"], origin="ai", source=None)

        links, seen = [], set()
        outside = {l["url"] for l in o.get("links_outside") or []}
        for l in (o.get("links_outside") or []) + [{"label": x.get("anchor") or x["url"], "url": x["url"], "page": x["page"]} for x in self.links]:
            if l["url"] in seen:
                continue
            seen.add(l["url"])
            links.append({"label": (l.get("label") or l["url"])[:120], "url": l["url"], "page": l.get("page"),
                          "outside_pattern": l["url"] in outside})

        for d in o.get("doubts") or []:
            self._doubt(d["kind"], d["message"], origin="ai", source=_source(d.get("page"), "", False) if d.get("page") else None)
        if self.picture_pages:
            pages = ", ".join(str(p) for p in sorted(self.picture_pages))
            self._doubt("from_picture", f"Page(s) {pages} had no usable text and were read from the picture. "
                                        "Check the numbers from those pages against the pattern.", source=None)

        return {
            "schema_version": "0.2",
            "build": {"pipeline": PIPELINE, "model": self.client.cfg.model, "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
            "pattern": {
                "title": o.get("title") or Path(self.pdf).stem, "designer": o.get("designer"), "publisher": o.get("publisher"),
                "pattern_number": o.get("pattern_number"), "language": o.get("language") or "en",
                "translated_from": o.get("translated_from"), "units_in_source": o.get("units_in_source") or "cm",
                "garment": o.get("garment"), "construction": o.get("construction"),
                "made_to_measure": bool(o.get("made_to_measure")), "summary": None,
            },
            "options": {"sizes": [{"id": i_, "label": l_} for i_, l_ in zip(size_ids, labels)],
                        "size_notation": notation, "choices": choices},
            "size_guide": {"kind": sg.get("kind") or "none", "page": sg.get("page"), "measurements": size_guide_rows},
            "gauge": gauge, "needles": needles, "yarns": yarns, "notions": notions, "abbreviations": abbreviations,
            "techniques": techniques, "charts": charts, "sections": out_sections, "pieces": [], "reminders": reminders,
            "links": links, "doubts": self.code_doubts,
        }

    def _step(self, sid, k, st, sec, n, labels, size_ids, notation, clabels, choice_ids, tech_by_name, chart_by_name) -> dict:
        text_src = sec["text"]
        loc = locate(st.get("quote"), text_src)
        picture = bool(st.get("from_picture")) or bool(set(sec["pages"]) & self.picture_pages)
        if loc:
            quote = text_src[loc[0]:loc[1]]
            pages = re.findall(r"=== Page (\d+) ===", text_src[: loc[0]])
            page = int(pages[-1]) if pages else (sec["pages"][0] if sec["pages"] else None)
            confidence = "high" if loc[2] == 1.0 else "medium"
        else:
            quote = st.get("quote") or ""
            page = st.get("page")
            confidence = "low"
        runs = sizes.find_runs(quote, n, notation=notation, size_labels=labels, choice_labels=clabels) if n > 1 or clabels else []
        self._check_runs(runs, f"{sec['outline']['name']}, step {k + 1}", step_id=f"{sid}-{k + 1}")
        text, slots = sizes.slot_text(quote, runs, n) if runs else (quote, [])
        for sl in slots:
            sl["value"]["from_picture"] = picture
            if sl["value"].get("by_choice"):
                for entry in sl["value"]["by_choice"]:
                    entry["choice"] = choice_ids.get(entry["choice"], entry["choice"])

        def q(sub, unit=None):
            if not sub:
                return None
            where = quote if loc else text_src
            l2 = locate(sub, where)
            src = where[l2[0]:l2[1]] if l2 else sub
            return sizes.quantity(src, n, notation=notation, prefer_unit=unit, size_labels=labels,
                                  choice_labels=clabels, choice_ids=choice_ids, from_picture=picture)

        kind = st.get("target_kind") or "none"
        target = {"kind": kind, "count": q(st.get("count_quote")), "length": q(st.get("length_quote"), "cm"),
                  "until_row": q(st.get("until_row_quote"), "rows"), "measured_from": st.get("measured_from"),
                  "ending": st.get("ending"), "match": {"text": quote[:200], "step_id": None} if kind == "match" else None}
        rp = st.get("repeat")
        repeat = None
        if rp:
            until_q = rp.get("until_quote")
            repeat = {"rows_in_repeat": q(rp.get("rows_quote"), "rows"), "times": q(rp.get("times_quote"), "times"),
                      "until_row": q(until_q, "rows") if until_q and re.search(r"\brow\s*\d", until_q, re.I) else None,
                      "until_text": until_q, "includes_first": rp.get("includes_first"), "includes_earlier_text": None}
        cp_q = st.get("checkpoint_quote")
        checkpoint = None
        if cp_q:
            total = q(cp_q, "stitches")
            checkpoint = {"kind": "stitches", "total": total, "parts": [], "text": cp_q[:200]}
        schedules = []
        for scq in st.get("schedules", []):
            until_q = scq.get("until_quote")
            schedules.append({
                "action": scq["action"], "slots": [], "every": q(scq.get("every_quote")), "every_unit": scq.get("every_unit"),
                "on_rows": q(scq.get("on_rows_quote"), "rows"), "times": q(scq.get("times_quote"), "times"),
                "first_at": None, "until": {"text": until_q, "stitches": q(until_q, "stitches")} if until_q else None,
                "checkpoint": None, "source": _source(page, scq.get("quote") or scq["action"], picture),
            })
        tech_ids = [tech_by_name[t.strip().lower()] for t in st.get("techniques", []) if t.strip().lower() in tech_by_name]
        chart_ids = [chart_by_name[c.strip().lower()] for c in st.get("charts", []) if c.strip().lower() in chart_by_name]
        applies = self._applies_from_note(st.get("sizes_note"), labels, size_ids)
        if applies is None:
            applies = self._applies_from_zero(target, repeat, size_ids)
        step_type = st.get("type") or "instruction"
        if step_type == "measure" and kind != "length":
            step_type = "instruction"
        if step_type == "repeat" and repeat is None:
            step_type = "rows"
        if confidence == "low":
            self._doubt("other", f"Step {k + 1} of \"{sec['outline']['name']}\" could not be matched word for word to "
                                 f"the pattern. Check it against page {page or '?'}.", step_ids=[f"{sid}-{k + 1}"])
        return {"id": f"{sid}-{k + 1}", "type": step_type, "text": text, "slots": slots, "applies_to": applies,
                "target": target, "repeat": repeat, "checkpoint": checkpoint, "schedules": schedules,
                "technique_ids": tech_ids, "chart_ids": chart_ids, "based_on": None, "optional": bool(st.get("optional")),
                "source": _source(page, quote, picture), "confidence": confidence}

    # ------------------------------------------------ small parsers
    def _needle(self, k, x, choice_ids, n, notation, labels) -> dict:
        t = x["text"]
        mm = re.search(r"(\d+(?:[.,]\d+)?)\s*mm", t, re.I)
        us = re.search(r"\bUS\s*#?\s*(\d+(?:[.,]\d+)?)|#\s*(\d+(?:[.,]\d+)?)\s*US", t, re.I)
        uk = re.search(r"\b(?:UK|Canadian)\s*(\d+(?:[-/]\d+)?)", t, re.I)
        kinds = [k_ for k_, pat in (("circular", r"circular"), ("double_pointed", r"double[- ]pointed|\bdpns?\b"),
                                    ("straight", r"straight"), ("crochet_hook", r"crochet hook|\bhook\b")) if re.search(pat, t, re.I)]
        length_m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:cm|-?inch(?:es)?|in\b|\")", t, re.I)
        return {"id": f"n{k + 1}", "text": t, "size_mm": mm.group(1) if mm else None,
                "size_us": (us.group(1) or us.group(2)) if us else None, "size_uk": uk.group(1) if uk else None,
                "kinds": kinds or ["other"],
                "length": None if not length_m else {"text": length_m.group(0), "unit": "cm" if "cm" in length_m.group(0) else "in",
                                                      "all": length_m.group(1), "by_size": None, "by_choice": None,
                                                      "from_picture": False, "alt": None},
                "use": None, "applies_to": {"sizes": None, "choices": [choice_ids[x["choice_value"]]], "except": []}
                if x.get("choice_value") in choice_ids else None,
                "source": _source(x.get("page"), t, x.get("page") in self.picture_pages)}

    def _gauge(self, x, choice_ids) -> dict:
        t = x["text"]
        st = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:sts?|stitches|m\b|masker)", t, re.I)
        rw = re.search(r"(\d+(?:[.,]\d+)?)\s*(rows|rounds|rnds|round pairs|row pairs)", t, re.I)
        over = re.search(r"(\d+(?:[.,]\d+)?\s*(?:x\s*\d+(?:[.,]\d+)?\s*)?(?:cm|in(?:ches)?|\"))", t, re.I)
        unit = None
        if rw:
            w = rw.group(2).lower()
            unit = "round_pairs" if "pair" in w else ("rounds" if w.startswith(("round", "rnd")) else "rows")
        return {"text": t, "stitches": st.group(1) if st else None, "rows": rw.group(1) if rw else None,
                "rows_unit": unit, "over": over.group(1) if over else None, "stitch_pattern": None,
                "condition": x.get("condition"),
                "applies_to": {"sizes": None, "choices": [choice_ids[x["choice_value"]]], "except": []}
                if x.get("choice_value") in choice_ids else None,
                "source": _source(x.get("page"), t, x.get("page") in self.picture_pages)}

    @staticmethod
    def _applies_from_note(note, labels, size_ids):
        """'sizes XL-XXXL only', 'S, M and L' -> applies_to with those sizes; None when no sizes are named."""
        if not note:
            return None
        found = []
        low = note.lower()
        # ranges like "XL-XXXL" or "XL to XXXL"
        for a, b_ in re.findall(r"([A-Za-z0-9/]+)\s*(?:-|–|to)\s*([A-Za-z0-9/]+)", note):
            la = [l_.lower() for l_ in labels]
            if a.lower() in la and b_.lower() in la:
                i0, i1 = la.index(a.lower()), la.index(b_.lower())
                found += size_ids[min(i0, i1): max(i0, i1) + 1]
        for lbl, sid in zip(labels, size_ids):
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(lbl.lower())}(?![A-Za-z0-9])", low):
                found.append(sid)
        found = [s for s in size_ids if s in set(found)]
        if not found or len(found) == len(size_ids):
            return None
        return {"sizes": found, "choices": None, "except": []}

    @staticmethod
    def _applies_from_zero(target, repeat, size_ids):
        """A step whose main count is 0 or '-' for some sizes does not apply to those sizes."""
        main = (repeat or {}).get("times") or target.get("count")
        vals = (main or {}).get("by_size")
        if not vals or len(vals) != len(size_ids):
            return None
        keep = [sid for sid, v in zip(size_ids, vals) if v not in ("0", "-")]
        if len(keep) == len(size_ids) or not keep:
            return None
        return {"sizes": keep, "choices": None, "except": []}

    def _check_runs(self, runs, where: str, step_id: str | None = None) -> None:
        for r in runs:
            if not r.length_ok:
                self._doubt("list_length", f"{where}: {r.note or 'the number of values does not match the number of sizes'} "
                                           f"(\"{r.text[:60]}\"). Check this against the pattern.",
                            step_ids=[step_id] if step_id else [])

    def _doubt(self, kind, message, *, origin="code", step_ids=None, source=None):
        d = {"kind": kind if kind in schemas.DOUBT_KINDS else "other", "message": message, "origin": origin,
             "step_ids": [s for s in (step_ids or [])], "target": None, "source": source}
        if d not in self.code_doubts:
            self.code_doubts.append(d)


def build_guide(pdf: str, client: ai.Client, *, report: Reporter = silent, workers: int = 6) -> BuildResult:
    """Build a format 0.2 guide from a pattern PDF. Never raises for a bad answer from the model: problems become
    doubts and entries in the report. Raises ai.AIError only when the outline itself cannot be obtained."""
    return Builder(pdf, client, report, workers).run()
