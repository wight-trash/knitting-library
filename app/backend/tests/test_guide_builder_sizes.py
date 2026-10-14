"""Tests for app.guide_builder.sizes. All pattern text here is made up for the tests."""

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.guide_builder.sizes import SizedRun, find_runs, quantity, slot_text, to_sized_value  # noqa: E402


def values(text, n, **kw):
    """Values of each run found in text."""
    return [r.values for r in find_runs(text, n, **kw)]


def first(text, n, **kw):
    runs = find_runs(text, n, **kw)
    if not runs:
        raise AssertionError(f"no run in {text!r}")
    return runs[0]


class RunInvariantTests(unittest.TestCase):
    def test_offsets_match_text(self):
        text = "Then knit 14-16-18-20 sts and turn; repeat 2 (3, 4, 5) times."
        for r in find_runs(text, 4):
            self.assertEqual(text[r.start:r.end], r.text)
            self.assertIsInstance(r, SizedRun)

    def test_runs_are_left_to_right_and_do_not_overlap(self):
        text = "Bind off 3-3-4-4 sts, then 2-2-2-3 sts, then 1 (1, 1, 2) st."
        runs = find_runs(text, 4)
        self.assertEqual([r.values for r in runs],
                         [["3", "3", "4", "4"], ["2", "2", "2", "3"], ["1", "1", "1", "2"]])
        for a, b in zip(runs, runs[1:]):
            self.assertLessEqual(a.end, b.start)

    def test_one_size_has_no_runs(self):
        self.assertEqual(find_runs("Cast on 40-44-48 sts", 1), [])

    def test_empty_text(self):
        self.assertEqual(find_runs("", 3), [])


class DashListTests(unittest.TestCase):
    def test_plain(self):
        r = first("Cast on 84-90-98-104-112-120 sts with the smaller needle.", 6)
        self.assertEqual(r.values, ["84", "90", "98", "104", "112", "120"])
        self.assertEqual(r.unit, "stitches")
        self.assertEqual(r.text, "84-90-98-104-112-120 sts")
        self.assertTrue(r.length_ok)
        self.assertIsNone(r.note)

    def test_halves(self):
        r = first("every 5½-5-4½ cm", 3)
        self.assertEqual(r.values, ["5½", "5", "4½"])
        self.assertEqual(r.unit, "cm")

    def test_zeros(self):
        self.assertEqual(first("increase 0-0-1-2-3 times", 5).values, ["0", "0", "1", "2", "3"])
        self.assertEqual(first("increase 0-0-1-2-3 times", 5).unit, "times")

    def test_highlighted_size_with_spaces(self):
        r = first("you need 150-200- 200 -250 g of colour A", 4)
        self.assertEqual(r.values, ["150", "200", "200", "250"])
        self.assertEqual(r.unit, "g")

    def test_one_sided_space(self):
        self.assertEqual(first("knit 12-14- 16-18 rows", 4).values, ["12", "14", "16", "18"])

    def test_en_dash(self):
        self.assertEqual(first("work 7–8–9 rounds", 3).values, ["7", "8", "9"])
        self.assertEqual(first("work 7–8–9 rounds", 3).unit, "rounds")

    def test_decimal_comma(self):
        self.assertEqual(first("needle 3,5-4-4,5 mm", 3).values, ["3,5", "4", "4,5"])

    def test_decimal_point(self):
        self.assertEqual(first("12.5-13-13.5 cm", 3).values, ["12.5", "13", "13.5"])

    def test_slash_between_groups(self):
        self.assertEqual(first("17-18-19 / 20-21-22 cm", 6).values, ["17", "18", "19", "20", "21", "22"])

    def test_children_size_labels_with_slashes(self):
        r = first("Size: 1 - 3/4 - 5/6 - 7/8 years", 4)
        self.assertEqual(r.values, ["1", "3/4", "5/6", "7/8"])

    def test_spaced_dashes_between_sizes_tight_inside_ranges(self):
        r = first("To fit chest 66 - 71-76 - 81-86 - 91-97 cm", 4)
        self.assertEqual(r.values, ["66", "71-76", "81-86", "91-97"])

    def test_spaced_values(self):
        self.assertEqual(first("15 - 16½ - 18 - 19¾ in", 4).values, ["15", "16½", "18", "19¾"])

    def test_wrong_length_kept_with_note(self):
        r = first("cast off 4-5-6-7-8 sts", 6)
        self.assertEqual(r.values, ["4", "5", "6", "7", "8"])
        self.assertFalse(r.length_ok)
        self.assertEqual(r.note, "5 values for 6 sizes")

    def test_too_many_values_not_trimmed(self):
        r = first("pick up 40-44-48-52-56 sts", 4)
        self.assertEqual(len(r.values), 5)
        self.assertFalse(r.length_ok)

    def test_filler_word_before_unit(self):
        r = first("cast on 6-6-8-8 new stitches", 4)
        self.assertEqual(r.text, "6-6-8-8 new stitches")
        self.assertEqual(r.unit, "stitches")

    def test_hyphenated_unit(self):
        self.assertEqual(first("there are 8-9-10 shoulder-stitches", 3).unit, "stitches")

    def test_two_values_when_two_sizes(self):
        self.assertEqual(first("knit 8-9 cm", 2, notation="dash list").values, ["8", "9"])

    def test_inch_marks(self):
        r = first('length 9"-10"-11"', 3)
        self.assertEqual(r.values, ["9", "10", "11"])
        self.assertEqual(r.unit, "in")


class ParenListTests(unittest.TestCase):
    def test_commas(self):
        r = first("Cast on 58 (64, 70, 76) sts.", 4)
        self.assertEqual(r.values, ["58", "64", "70", "76"])
        self.assertEqual(r.unit, "stitches")
        self.assertEqual(r.text, "58 (64, 70, 76) sts")

    def test_colons(self):
        self.assertEqual(first("measures 79 (89:99:109) cm", 4).values, ["79", "89", "99", "109"])

    def test_semicolons(self):
        self.assertEqual(first("knit 3 (4; 5) rows", 3).values, ["3", "4", "5"])

    def test_square_brackets_with_colons(self):
        self.assertEqual(first("Cast on 36 [40:44:48] sts", 4).values, ["36", "40", "44", "48"])

    def test_curly_brackets(self):
        self.assertEqual(first("Cast on 36 {40, 44} sts", 3).values, ["36", "40", "44"])

    def test_ranges_as_values(self):
        r = first("To fit 76-81 (86-91:96-102) cm", 3)
        self.assertEqual(r.values, ["76-81", "86-91", "96-102"])
        self.assertEqual(r.unit, "cm")

    def test_stray_space_inside_range(self):
        self.assertEqual(first("bust 104 -109 (114-119) cm", 2).values, ["104 -109", "114-119"])

    def test_dashes_inside_brackets(self):
        r = first("Cast on 92 (98-104-110) sts.", 4)
        self.assertEqual(r.values, ["92", "98", "104", "110"])

    def test_fractions(self):
        self.assertEqual(first("work until 5¼ (6½, 7, 8¾) inches", 4).values, ["5¼", "6½", "7", "8¾"])
        self.assertEqual(first("work until 5¼ (6½, 7, 8¾) inches", 4).unit, "in")

    def test_decimals_and_decimal_commas(self):
        self.assertEqual(first("42.5 (46, 49.5) cm", 3).values, ["42.5", "46", "49.5"])
        self.assertEqual(first("4,5 (5, 5,5) cm", 3).values, ["4,5", "5", "5,5"])

    def test_unspaced_commas(self):
        self.assertEqual(first("Cast on 52 (56,60,64) sts", 4).values, ["52", "56", "60", "64"])

    def test_placeholders(self):
        r = first("Increase - (-, -, 0, 2) more times", 5)
        self.assertEqual(r.values, ["-", "-", "-", "0", "2"])
        self.assertEqual(r.unit, "times")

    def test_number_word_first(self):
        r = first("Work rows 1-2 four (5, 6, 7) more times", 4)
        self.assertEqual(r.values, ["four", "5", "6", "7"])
        self.assertEqual(r.text, "four (5, 6, 7) more times")

    def test_n_a_means_not_this_size(self):
        self.assertEqual(first("every 4th (n/a, 6th) round", 3).values, ["4th", "-", "6th"])

    def test_wrong_length(self):
        r = first("Knit 22 (24, 26, 28, 30) sts", 4)
        self.assertEqual(r.values, ["22", "24", "26", "28", "30"])
        self.assertFalse(r.length_ok)
        self.assertEqual(r.note, "5 values for 4 sizes")

    def test_only_brackets(self):
        self.assertEqual(first("Cast on (44, 48, 52) sts", 3).values, ["44", "48", "52"])

    def test_list_ends_at_its_bracket(self):
        r = first("Knit 5 (6, 7) 2.5oz skeins", 3)
        self.assertEqual(r.values, ["5", "6", "7"])

    def test_inches_and_cm_lists_side_by_side(self):
        runs = find_runs("measures 21½ (22-22¾-23½) ins [54.5 (56-58-59.5) cm]", 4)
        self.assertEqual([r.values for r in runs],
                         [["21½", "22", "22¾", "23½"], ["54.5", "56", "58", "59.5"]])
        self.assertEqual([r.unit for r in runs], ["in", "cm"])
        self.assertEqual(runs[1].note, "unit conversion of the previous value")


class AlternatingTests(unittest.TestCase):
    def test_four(self):
        self.assertEqual(first("1 (2) 3 (4)", 4).values, ["1", "2", "3", "4"])

    def test_odd_count(self):
        r = first("Cast on 88 (96) 104 (112) 120 sts", 5)
        self.assertEqual(r.values, ["88", "96", "104", "112", "120"])
        self.assertEqual(r.unit, "stitches")

    def test_stray_bracket(self):
        r = first("Knit ((3) 4 (4) 4 sts", 4)
        self.assertEqual(r.values, ["3", "4", "4", "4"])
        self.assertIn("stray bracket", r.note)

    def test_placeholders(self):
        r = first("Repeat - (-) - (-) 3 (3) 5 (5) times", 8)
        self.assertEqual(r.values, ["-", "-", "-", "-", "3", "3", "5", "5"])

    def test_stray_space(self):
        self.assertEqual(first("k 5 (6 ) - (-) 8 (-)", 6).values, ["5", "6", "-", "-", "8", "-"])

    def test_ranges(self):
        r = first("Chest 60–65 (70–75) 80–85 (90–95) cm", 4)
        self.assertEqual(r.values, ["60–65", "70–75", "80–85", "90–95"])

    def test_inch_marks_on_each_value(self):
        r = first("5.5” (5.5”) 6.1” (6.4”)", 4)
        self.assertEqual(r.values, ["5.5", "5.5", "6.1", "6.4"])
        self.assertEqual(r.unit, "in")

    def test_wrong_length(self):
        r = first("30 (32) 34 (36) 38 (40) 42 (44) 46 (48) cm", 9)
        self.assertEqual(len(r.values), 10)
        self.assertFalse(r.length_ok)
        self.assertEqual(r.note, "10 values for 9 sizes")

    def test_missing_brackets_around_last_value(self):
        r = first("8 (10) 12 (12) 15 17 times", 6)
        self.assertEqual(r.values, ["8", "10", "12", "12", "15", "17"])
        self.assertIn("brackets missing", r.note)

    def test_second_bare_value_not_taken_when_count_already_right(self):
        r = first("Knit 2 (3) 4 5 rows", 3)
        self.assertEqual(r.values, ["2", "3", "4"])

    def test_after_size_word_gets_a_note(self):
        r = first("Sizes 2 (4) 6 (8) only:", 8)
        self.assertIn("size labels", r.note)


class OrdinalTests(unittest.TestCase):
    def test_th(self):
        r = first("decrease every 7th (6th) 5th row", 3)
        self.assertEqual(r.values, ["7th", "6th", "5th"])
        self.assertEqual(r.unit, "rows")

    def test_commas_between_ordinals(self):
        self.assertEqual(first("every 14th, (12th), 10th round", 3).values, ["14th", "12th", "10th"])

    def test_dot_ordinals(self):
        r = first("decrease every 8. (7.) 6. row", 3)
        self.assertEqual(r.values, ["8.", "7.", "6."])
        self.assertEqual(r.unit, "rows")

    def test_sentence_full_stop_is_not_an_ordinal(self):
        r = first("Cast on 40 (44) 48.", 3)
        self.assertEqual(r.values, ["40", "44", "48"])
        self.assertEqual(r.text, "40 (44) 48")

    def test_st_after_six_is_stitches(self):
        r = first("bind off 6-7-8st", 3)
        self.assertEqual(r.values, ["6", "7", "8"])
        self.assertEqual(r.unit, "stitches")

    def test_paren_list_of_ordinals(self):
        self.assertEqual(first("every 3rd (4th, 4th, 5th) row", 4).values, ["3rd", "4th", "4th", "5th"])


class StitchWordTests(unittest.TestCase):
    def test_purl_knit(self):
        self.assertEqual(first("then p (k) p (k) to end", 4).values, ["p", "k", "p", "k"])

    def test_words(self):
        self.assertEqual(first("knit (purl) knit", 3).values, ["knit", "purl", "knit"])

    def test_stitch_words_need_the_full_count(self):
        self.assertEqual(find_runs("work p (k) to end", 4), [])


class GroupedBracketTests(unittest.TestCase):
    def test_three_groups(self):
        r = first("Cast on (50, 54, 58) [62, 66, 70] {74, 78, 82} sts", 9)
        self.assertEqual(r.values, ["50", "54", "58", "62", "66", "70", "74", "78", "82"])
        self.assertEqual(r.unit, "stitches")

    def test_x_means_not_this_size(self):
        r = first("Repeat (2, X, 3) [X, 4, 4] {5, 5, X} times", 9)
        self.assertEqual(r.values, ["2", "-", "3", "-", "4", "4", "5", "5", "-"])

    def test_grouped_hint_allows_single_group(self):
        r = first("Knit (10, 12) sts", 3, notation="(a, b, c) [d, e, f]")
        self.assertEqual(r.values, ["10", "12"])
        self.assertFalse(r.length_ok)

    def test_single_group_needs_count_without_hint(self):
        self.assertEqual(find_runs("Knit (10, 12) sts", 3), [])


class LabelTests(unittest.TestCase):
    LABELS = ["XS", "S", "M", "L"]

    def test_label_prefixed(self):
        r = first("Chest: XS 80, S 84, M 88, L 92 cm", 4, size_labels=self.LABELS)
        self.assertEqual(r.values, ["80", "84", "88", "92"])
        self.assertTrue(r.length_ok)

    def test_label_with_colon(self):
        r = first("XS: 3, S: 3, M: 4, L: 5", 4, size_labels=self.LABELS)
        self.assertEqual(r.values, ["3", "3", "4", "5"])

    def test_missing_labels_left_empty(self):
        r = first("XS 80, M 88", 4, size_labels=self.LABELS)
        self.assertEqual(r.values, ["80", None, "88", None])
        self.assertFalse(r.length_ok)
        self.assertIn("values for 2 of 4 sizes", r.note)

    def test_label_ranges(self):
        r = first("the marker is on row 15 (XS - S) / row 18 (M - L) of the chart", 4, size_labels=self.LABELS)
        self.assertEqual(r.values, ["15", "15", "18", "18"])

    def test_m1l_is_not_a_label(self):
        self.assertEqual(find_runs("k1, M1L, k2, M1R", 4, size_labels=self.LABELS), [])


class TableRowTests(unittest.TestCase):
    def test_space_separated_row(self):
        r = first("Colour B 3 3 4 5 balls", 4)
        self.assertEqual(r.values, ["3", "3", "4", "5"])
        self.assertEqual(r.unit, "balls")

    def test_needs_exact_count(self):
        self.assertEqual(find_runs("Colour B 3 3 4 balls", 4), [])


class ByChoiceTests(unittest.TestCase):
    CHOICES = ["fingering", "sport", "dk", "worsted"]

    def test_block(self):
        text = "fingering: 90 (96, 102); sport: 80 (86, 92); dk: 70 (74, 78); worsted: 60 (64, 68) sts"
        runs = find_runs(text, 3, choice_labels=self.CHOICES)
        self.assertEqual(len(runs), 1)
        r = runs[0]
        self.assertEqual(r.kind, "by_choice")
        self.assertEqual(r.values, [])
        self.assertEqual(r.by_choice["fingering"], ["90", "96", "102"])
        self.assertEqual(r.by_choice["worsted"], ["60", "64", "68"])
        self.assertTrue(r.length_ok)
        self.assertEqual(r.text, text)

    def test_block_on_lines(self):
        text = "Fingering: 12 (13, 14)\nDK: 10 (11, 12)"
        r = first(text, 3, choice_labels=self.CHOICES)
        self.assertEqual(r.by_choice, {"fingering": ["12", "13", "14"], "dk": ["10", "11", "12"]})

    def test_one_value_per_choice(self):
        r = first("fingering: 21\ndk: 17", 3, choice_labels=self.CHOICES)
        self.assertEqual(r.by_choice, {"fingering": ["21", "21", "21"], "dk": ["17", "17", "17"]})
        self.assertIn("one value for every size", r.note)

    def test_wrong_length_in_one_choice(self):
        r = first("fingering: 5 (6) ; dk: 4 (5, 6)", 3, choice_labels=self.CHOICES)
        self.assertFalse(r.length_ok)
        self.assertIn("2 values for 3 sizes", r.note)

    def test_n_a(self):
        r = first("sport: 7 (n/a, 9) times", 3, choice_labels=self.CHOICES)
        self.assertEqual(r.by_choice, {"sport": ["7", "-", "9"]})

    def test_one_size_with_choices(self):
        text = "fingering: 220 yds; dk: 180 yds; and 40-44 sts"
        r = first(text, 1, choice_labels=self.CHOICES)
        self.assertEqual(r.by_choice, {"fingering": ["220"], "dk": ["180"]})
        self.assertEqual(r.unit, "yd")
        self.assertEqual(len(find_runs(text, 1, choice_labels=self.CHOICES)), 1)

    def test_without_choice_labels_lines_are_plain_runs(self):
        self.assertEqual(values("fingering: 90 (96, 102); dk: 70 (74, 78)", 3),
                         [["90", "96", "102"], ["70", "74", "78"]])


class MustNotTests(unittest.TestCase):
    CASES = [
        ("Pattern DROPS 231-47", 6),
        ("Pattern DROPS 231-47-2", 3),
        ("design ab-312", 3),
        ("work from *-* 3 times", 3),
        ("repeat rows 1-4", 4),
        ("Repeat Rows 1 to 4", 4),
        ("a top-down raglan", 3),
        ("k1, M1L, k2tog, ssk", 3),
        ("published 2023-11-05", 3),
        ("approx. 6-7 cm", 4),
        ("gauge: 22 sts and 30 rows = 10 x 10 cm", 4),
        ("see page 12", 3),
        ("see pages 4-5", 4),
        ("US 4 (3.5 mm)", 2),
        ("needle 3.5 mm (US 4)", 2),
        ("102 cm [40¼ in]", 2),
        ("7mm [US 10.5]", 2),
        ("Row 1 (RS): k2, p2", 2),
        ("work chart A.2 (14 rows)", 2),
        ("rows 10, 20, 30 and 40", 4),
        ("40 cm and 80 cm long", 2),
        ("R12 - R15", 2),
        ("arrow-2 in chart", 2),
        ("rounds 1-12 of A.1", 2),
        ("1.75oz/50g balls", 2),
        ("in 4 ply yarn", 3),
        ("cast on 60 sts (see note)", 3),
    ]

    def test_not_size_lists(self):
        for text, n in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(find_runs(text, n), [])

    def test_dash_hint_rejects_bracket_lists_of_wrong_length(self):
        self.assertEqual(find_runs("every 2nd (4th) row", 6, notation="dash list"), [])

    def test_bracket_hint_rejects_short_dash_pair(self):
        self.assertEqual(find_runs("knit 8-9 cm", 2, notation="a (b)"), [])

    def test_conversion_beside_list_is_not_a_value(self):
        r = first("4 (4.5) mm [US 6]", 2)
        self.assertEqual(r.values, ["4", "4.5"])
        self.assertEqual(len(find_runs("4 (4.5) mm [US 6]", 2)), 1)


class NotationHintTests(unittest.TestCase):
    def test_hint_picks_ranges(self):
        r = first("To fit 80-85 (90-95)", 2, notation="a (b)")
        self.assertEqual(r.values, ["80-85", "90-95"])

    def test_count_picks_split(self):
        r = first("To fit 80 (85-90)", 3, notation="a (b-c)")
        self.assertEqual(r.values, ["80", "85", "90"])

    def test_unhelpful_hint_is_ignored(self):
        self.assertEqual(first("Knit 4-5-6 rows", 3, notation="whatever").values, ["4", "5", "6"])


class ToSizedValueTests(unittest.TestCase):
    def test_from_run(self):
        r = first("Knit 10 (12, 14) rows", 3)
        sv = to_sized_value(r, 3)
        self.assertEqual(sv, {"text": "10 (12, 14) rows", "unit": "rows", "all": None,
                              "by_size": ["10", "12", "14"], "by_choice": None, "from_picture": False,
                              "alt": None})

    def test_unit_override_and_picture(self):
        r = first("Knit 10 (12, 14) rows", 3)
        sv = to_sized_value(r, 3, unit="rounds", from_picture=True, text="Knit 10 (12, 14)")
        self.assertEqual(sv["unit"], "rounds")
        self.assertTrue(sv["from_picture"])
        self.assertEqual(sv["text"], "Knit 10 (12, 14)")

    def test_single(self):
        sv = to_sized_value(None, 3, text="4 cm", single="4", unit="cm")
        self.assertEqual(sv["all"], "4")
        self.assertIsNone(sv["by_size"])
        self.assertEqual(sv["unit"], "cm")

    def test_not_given(self):
        sv = to_sized_value(None, 3, text="")
        self.assertEqual((sv["all"], sv["by_size"], sv["by_choice"]), (None, None, None))

    def test_by_choice_ids(self):
        r = first("fingering: 3 (4); dk: 2 (3)", 2, choice_labels=["fingering", "dk"])
        sv = to_sized_value(r, 2, choice_ids={"fingering": "fg", "dk": "dk8"})
        self.assertIsNone(sv["by_size"])
        self.assertEqual(sv["by_choice"], [{"choice": "fg", "by_size": ["3", "4"]},
                                           {"choice": "dk8", "by_size": ["2", "3"]}])

    def test_wrong_length_copied_as_is(self):
        r = first("Knit 10 (12, 14, 16) rows", 3)
        self.assertEqual(to_sized_value(r, 3)["by_size"], ["10", "12", "14", "16"])


class SlotTextTests(unittest.TestCase):
    def test_slots(self):
        text = "Cast on 60 (66, 72) sts and knit 4 (4, 5) cm."
        new, slots = slot_text(text, find_runs(text, 3), 3)
        self.assertEqual(new, "Cast on {s1} sts and knit {s2} cm.")
        self.assertEqual([s["name"] for s in slots], ["s1", "s2"])
        self.assertEqual(slots[0]["value"]["by_size"], ["60", "66", "72"])
        self.assertEqual(slots[0]["value"]["text"], "60 (66, 72) sts")
        self.assertEqual(slots[1]["value"]["unit"], "cm")

    def test_prefix_and_dash_lists(self):
        text = "Decrease 2-2-3 times every 4-4-3½ cm."
        new, slots = slot_text(text, find_runs(text, 3), 3, prefix="v")
        self.assertEqual(new, "Decrease {v1} times every {v2} cm.")
        self.assertEqual(slots[1]["value"]["by_size"], ["4", "4", "3½"])

    def test_no_runs(self):
        self.assertEqual(slot_text("Knit 2 rows.", [], 3), ("Knit 2 rows.", []))

    def test_by_choice_block_replaced_whole(self):
        text = "Knit fingering: 3 (4); dk: 2 (3) rounds."
        runs = find_runs(text, 2, choice_labels=["fingering", "dk"])
        new, slots = slot_text(text, runs, 2)
        self.assertEqual(new, "Knit {s1}.")
        self.assertIsNotNone(slots[0]["value"]["by_choice"])


class QuantityTests(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(quantity(None, 3))
        self.assertIsNone(quantity("knit to the end", 3))

    def test_dash_run(self):
        sv = quantity("work 5-7-9 rounds", 3)
        self.assertEqual(sv["by_size"], ["5", "7", "9"])
        self.assertEqual(sv["unit"], "rounds")

    def test_single_length(self):
        sv = quantity("until the piece measures 32 cm", 3)
        self.assertEqual(sv["all"], "32")
        self.assertEqual(sv["unit"], "cm")
        self.assertEqual(sv["text"], "32 cm")
        self.assertIsNone(sv["by_size"])

    def test_paren_times(self):
        sv = quantity("repeat 2 (3, 4) times", 3)
        self.assertEqual(sv["by_size"], ["2", "3", "4"])
        self.assertEqual(sv["unit"], "times")

    def test_equals_stitches(self):
        sv = quantity("= 148 (160) sts", 2)
        self.assertEqual(sv["by_size"], ["148", "160"])

    def test_ordinal(self):
        sv = quantity("every 6th row", 3)
        self.assertEqual(sv["all"], "6th")
        self.assertEqual(sv["unit"], "rows")

    def test_prefer_unit_picks_run(self):
        sv = quantity("decrease 1 st 3 (4, 5) times every 6 (6, 4) rows", 3, prefer_unit="rows")
        self.assertEqual(sv["by_size"], ["6", "6", "4"])

    def test_prefer_unit_picks_single_over_other_run(self):
        sv = quantity("Knit 2 rows over the 44 (48, 52) sts", 3, prefer_unit="rows")
        self.assertEqual(sv["all"], "2")
        self.assertEqual(sv["unit"], "rows")

    def test_total_after_equals(self):
        sv = quantity("increase 8-8-10 sts evenly = 96-104-112 sts", 3, prefer_unit="stitches")
        self.assertEqual(sv["by_size"], ["96", "104", "112"])

    def test_until_row(self):
        sv = quantity("Repeat rows 3-6 until row 40, then every 2 rows", 1, prefer_unit="rows")
        self.assertEqual(sv["all"], "40")

    def test_conversion_prefers_unit(self):
        sv = quantity("rib for 2 ins [5 cm]", 3, prefer_unit="in")
        self.assertEqual(sv["all"], "2")
        sv = quantity("rib for 2 ins [5 cm]", 3, prefer_unit="cm")
        self.assertEqual(sv["all"], "5")

    def test_number_word(self):
        self.assertEqual(quantity("repeat two more times", 3)["all"], "two")

    def test_range_for_all_sizes(self):
        sv = quantity("approx. 8-9 cm", 4)
        self.assertEqual(sv["all"], "8-9")
        self.assertEqual(sv["unit"], "cm")

    def test_one_size(self):
        sv = quantity("Cast on 40-44 sts", 1)
        self.assertEqual(sv["all"], "40-44")

    def test_by_choice(self):
        sv = quantity("fingering: 9 (10); dk: 7 (8) rows", 2, choice_labels=["fingering", "dk"],
                      choice_ids={"fingering": "f", "dk": "d"})
        self.assertEqual(sv["by_choice"][0], {"choice": "f", "by_size": ["9", "10"]})

    def test_from_picture(self):
        self.assertTrue(quantity("knit 4 rows", 2, from_picture=True)["from_picture"])

    def test_row_reference_skipped_for_count(self):
        sv = quantity("Row 5: knit 3 sts", 2)
        self.assertEqual(sv["all"], "3")


if __name__ == "__main__":
    unittest.main()
