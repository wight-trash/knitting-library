"""Guide builder: quote matching, progress events, size notes, and a full build with a pretend model.

All pattern text here is made up.
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.guide_builder import ai, schemas
from app.guide_builder.pipeline import Builder, build_guide, locate
from app.guide_builder.progress import Event


class LocateTests(unittest.TestCase):
    TEXT = "=== Page 2 ===\nYOKE\nCast on 96-104-112 sts on circular needle 4 mm.\nWork rib for 3 cm."

    def test_exact(self):
        s, e, score = locate("Cast on 96-104-112 sts", self.TEXT)
        self.assertEqual(self.TEXT[s:e], "Cast on 96-104-112 sts")
        self.assertEqual(score, 1.0)

    def test_whitespace_dashes_ligatures_and_case(self):
        text = "Work in pattern until the piece mea-\nsures 30 cm – ﬁnish with a WS row."
        loc = locate("work in pattern until the piece mea- sures 30 cm - finish with a WS row", text)
        self.assertIsNotNone(loc)
        self.assertTrue(text[loc[0]:loc[1]].startswith("Work in pattern"))

    def test_near_match_is_found_but_scored_lower(self):
        loc = locate("Cast on 96-104-112 stitches on circular needle 4 mm", self.TEXT)
        self.assertIsNotNone(loc)
        self.assertLess(loc[2], 1.0)

    def test_unrelated_quote_is_not_found(self):
        self.assertIsNone(locate("Sew the buttons on the left front band", self.TEXT))

    def test_empty(self):
        self.assertIsNone(locate("", self.TEXT))
        self.assertIsNone(locate(None, self.TEXT))


class ProgressTests(unittest.TestCase):
    def test_percent_rises_through_the_stages(self):
        seq = [Event("read", ""), Event("pictures", "", 1, 2), Event("outline", ""), Event("sections", "", 0, 4),
               Event("sections", "", 4, 4), Event("checks", ""), Event("done", "")]
        values = [e.percent for e in seq]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[-1], 100)
        self.assertIn("title", seq[0].as_dict())


class SizeNoteTests(unittest.TestCase):
    labels = ["S", "M", "L", "XL", "XXL", "XXXL"]
    ids = ["s", "m", "l", "xl", "xxl", "xxxl"]

    def test_range(self):
        a = Builder._applies_from_note("sizes XL-XXXL only", self.labels, self.ids)
        self.assertEqual(a["sizes"], ["xl", "xxl", "xxxl"])

    def test_list(self):
        a = Builder._applies_from_note("S, M and L", self.labels, self.ids)
        self.assertEqual(a["sizes"], ["s", "m", "l"])

    def test_no_sizes_named(self):
        self.assertIsNone(Builder._applies_from_note("only if you want a longer cuff", self.labels, self.ids))

    def test_zero_counts_drop_sizes(self):
        target = {"count": None}
        repeat = {"times": {"by_size": ["0", "0", "0", "3", "4", "8"]}}
        a = Builder._applies_from_zero(target, repeat, self.ids)
        self.assertEqual(a["sizes"], ["xl", "xxl", "xxxl"])


# ---------------------------------------------------------------- end to end with a pretend model
LINES = [
    "Example Hat (made up for tests)",
    "SIZES: S - M - L",
    "YARN: Any DK wool 50-100-100 g",
    "NEEDLES: circular needle 4 mm, 40 cm",
    "GAUGE: 22 sts and 30 rounds = 10 x 10 cm",
    "BRIM",
    "Cast on 96-104-112 sts. Work rib for 5 cm.",
    "CROWN",
    "Next round: k2tog to end = 48-52-56 sts.",
]


def tiny_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with the given lines of Helvetica text and a correct cross-reference table."""
    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = " ".join(f"BT /F1 11 Tf 60 {780 - 18 * k} Td ({esc(t)}) Tj ET" for k, t in enumerate(lines)).encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(ops), ops),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for k, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (k, body)
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    return bytes(out)


OUTLINE = {
    "title": "Example Hat", "designer": None, "publisher": None, "pattern_number": None, "language": "en",
    "translated_from": None, "garment": "hat", "construction": "in the round", "units_in_source": "cm",
    "made_to_measure": False, "sizes": ["S", "M", "L"], "size_notation": "dash list", "choices": [],
    "size_guide": {"kind": "none", "page": None, "rows": []},
    "yarns": [{"name": "Any DK wool", "weight": "DK", "fibre": "wool", "ball": None, "colour": None, "strand_group": None,
               "alternative_group": None, "alternatives_text": None, "amount_quote": "50-100-100 g", "page": 1,
               "from_picture": False, "choice_value": None}],
    "needles": [{"text": "circular needle 4 mm, 40 cm", "page": 1, "choice_value": None}],
    "notions": [], "gauge": [{"text": "22 sts and 30 rounds = 10 x 10 cm", "page": 1, "condition": None, "choice_value": None}],
    "abbreviations": [{"abbr": "k2tog", "meaning": "knit 2 together", "defined": False}],
    "techniques": [], "charts": [],
    "sections": [
        {"name": "Brim", "first_page": 1, "last_page": 1, "start_quote": "BRIM", "instances": [], "mirrored": False,
         "implied": False, "based_on_section": None},
        {"name": "Crown", "first_page": 1, "last_page": 1, "start_quote": "CROWN", "instances": [], "mirrored": False,
         "implied": False, "based_on_section": None},
    ],
    "links_outside": [], "doubts": [],
}


def step(quote, **kw):
    base = {"type": "instruction", "quote": quote, "page": 1, "target_kind": "none", "count_quote": None,
            "length_quote": None, "until_row_quote": None, "measured_from": None, "ending": None, "repeat": None,
            "checkpoint_quote": None, "schedules": [], "techniques": [], "charts": [], "sizes_note": None,
            "optional": False, "from_picture": False}
    base.update(kw)
    return base


SECTIONS = {
    "Brim": {"steps": [step("Cast on 96-104-112 sts."),
                       step("Work rib for 5 cm.", type="measure", target_kind="length", length_quote="5 cm")],
             "reminders": [], "doubts": []},
    "Crown": {"steps": [step("Next round: k2tog to end = 48-52-56 sts.", type="rows", target_kind="rounds",
                             count_quote="Next round", checkpoint_quote="= 48-52-56 sts")],
              "reminders": [], "doubts": []},
}


class FakeClient:
    """Answers like the model would, from canned data. Records what it was asked."""
    def __init__(self):
        self.cfg = ai.AIConfig(api_key="test", model="fake/model")
        self.calls = []

    def json(self, system, content, schema, name, **kw):
        self.calls.append(name)
        if name == "pattern_outline":
            data = OUTLINE
        else:
            text = " ".join(p.get("text", "") for p in content if p["type"] == "text")
            section = "Crown" if "Section: Crown" in text else "Brim"
            data = SECTIONS[section]
        return ai.Answer(json.loads(json.dumps(data)), "strict", {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001})

    def text(self, system, content, **kw):
        self.calls.append("picture")
        return ai.Answer({"text": "(no pattern content)"}, "text", {})


class EndToEndTests(unittest.TestCase):
    def test_build_with_pretend_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "hat.pdf"
            pdf.write_bytes(tiny_pdf(LINES))
            events = []
            client = FakeClient()
            res = build_guide(str(pdf), client, report=events.append, workers=2)
        guide = res.guide
        self.assertEqual(schemas.problems(guide), [])
        self.assertEqual([s["label"] for s in guide["options"]["sizes"]], ["S", "M", "L"])
        self.assertEqual([s["name"] for s in guide["sections"]], ["Brim", "Crown"])
        cast_on = guide["sections"][0]["steps"][0]
        self.assertEqual(cast_on["confidence"], "high")
        self.assertEqual(cast_on["slots"][0]["value"]["by_size"], ["96", "104", "112"])
        self.assertIn("{s1}", cast_on["text"])
        crown = guide["sections"][1]["steps"][0]
        self.assertEqual(crown["checkpoint"]["total"]["by_size"], ["48", "52", "56"])
        self.assertEqual(guide["yarns"][0]["amount"]["by_size"], ["50", "100", "100"])
        self.assertEqual(guide["needles"][0]["size_mm"], "4")
        self.assertEqual(guide["gauge"][0]["stitches"], "22")
        stages = [e.stage for e in events]
        self.assertEqual(stages[0], "read")
        self.assertEqual(stages[-1], "done")
        self.assertIn("sections", stages)
        self.assertEqual(client.calls.count("pattern_section"), 2)
        self.assertEqual(res.report["calls"], 3)

    def test_heartbeat_keeps_progress_moving_during_slow_calls(self):
        import time as _time
        from app.guide_builder import pipeline as pl

        class SlowClient(FakeClient):
            def json(self, *a, **kw):
                _time.sleep(0.3)
                return super().json(*a, **kw)

        old = pl.HEARTBEAT_SECONDS
        pl.HEARTBEAT_SECONDS = 0.05
        try:
            with tempfile.TemporaryDirectory() as tmp:
                pdf = Path(tmp) / "hat.pdf"
                pdf.write_bytes(tiny_pdf(LINES))
                events = []
                build_guide(str(pdf), SlowClient(), report=events.append, workers=2)
        finally:
            pl.HEARTBEAT_SECONDS = old
        beats = [e for e in events if e.detail.get("heartbeat")]
        self.assertTrue(beats, "no heartbeat events while the model was answering")
        self.assertTrue(all("elapsed" in e.detail for e in beats))
        self.assertEqual(events[-1].stage, "done")

    def test_quote_not_in_pattern_becomes_a_doubt(self):
        bad = json.loads(json.dumps(SECTIONS))
        bad["Brim"]["steps"][0]["quote"] = "Cast on 200 stitches using the long-tail method and join."
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "hat.pdf"
            pdf.write_bytes(tiny_pdf(LINES))
            client = FakeClient()
            original = SECTIONS["Brim"]
            SECTIONS["Brim"] = bad["Brim"]
            try:
                res = build_guide(str(pdf), client, workers=2)
            finally:
                SECTIONS["Brim"] = original
        step0 = res.guide["sections"][0]["steps"][0]
        self.assertEqual(step0["confidence"], "low")
        self.assertTrue(any(d["origin"] == "code" and step0["id"] in d["step_ids"] for d in res.guide["doubts"]))


if __name__ == "__main__":
    unittest.main()
