"""Tests for app.guide_builder.units."""

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.guide_builder.units import (  # noqa: E402
    cable_length_cm,
    display_cm,
    gauge_per_10cm,
    needle_mm,
    parse_number,
    parse_range,
    round_pairs_to_rounds,
    to_cm,
    to_grams,
    to_metres,
)


class ParseNumberTests(unittest.TestCase):
    def test_numbers(self):
        cases = {
            "4": 4.0, "4½": 4.5, "4,5": 4.5, "4.5": 4.5, "17 ½": 17.5, "¾": 0.75, "2¼": 2.25, "three": 3.0,
            "Three": 3.0, "twice": 2.0, "1/2": 0.5, "1 1/2": 1.5, "0": 0.0, "6th": 6.0, "2nd": 2.0, "9.": 9.0,
            '6.9”': 6.9, '10"': 10.0, " 12 ": 12.0, "1,240": 1240.0, "0,125": 0.125,
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertAlmostEqual(parse_number(text), want)

    def test_not_numbers(self):
        for text in ["65-70", "4–5", "-", "X", "n/a", "", "abc", "k2tog", None, "1/0"]:
            with self.subTest(text=text):
                self.assertIsNone(parse_number(text))


class ParseRangeTests(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(parse_range("65-70"), (65.0, 70.0))
        self.assertEqual(parse_range("4–5"), (4.0, 5.0))
        self.assertEqual(parse_range("4 - 5½"), (4.0, 5.5))
        self.assertEqual(parse_range("8 to 9"), (8.0, 9.0))
        self.assertEqual(parse_range("112 -117"), (112.0, 117.0))

    def test_single(self):
        self.assertEqual(parse_range("12"), (12.0, 12.0))
        self.assertEqual(parse_range("4½"), (4.5, 4.5))

    def test_bad(self):
        self.assertIsNone(parse_range("-"))
        self.assertIsNone(parse_range("a-b"))
        self.assertIsNone(parse_range(""))


class ConversionTests(unittest.TestCase):
    def test_to_cm(self):
        self.assertAlmostEqual(to_cm(10, "in"), 25.4)
        self.assertAlmostEqual(to_cm(2, "inches"), 5.08)
        self.assertAlmostEqual(to_cm(1, '"'), 2.54)
        self.assertAlmostEqual(to_cm(1, "”"), 2.54)
        self.assertAlmostEqual(to_cm(7, "cm"), 7.0)
        self.assertAlmostEqual(to_cm(45, "mm"), 4.5)
        self.assertAlmostEqual(to_cm(1.5, "m"), 150.0)
        self.assertIsNone(to_cm(3, "stones"))

    def test_to_metres(self):
        self.assertAlmostEqual(to_metres(100, "yd"), 91.44)
        self.assertAlmostEqual(to_metres(100, "yards"), 91.44)
        self.assertAlmostEqual(to_metres(50, "m"), 50.0)
        self.assertIsNone(to_metres(3, "g"))

    def test_to_grams(self):
        self.assertAlmostEqual(to_grams(1, "oz"), 28.3495)
        self.assertAlmostEqual(to_grams(3.5, "oz"), 99.22325)
        self.assertAlmostEqual(to_grams(50, "g"), 50.0)
        self.assertIsNone(to_grams(1, "yd"))


class NeedleTests(unittest.TestCase):
    def test_metric(self):
        self.assertEqual(needle_mm("4.5 mm"), 4.5)
        self.assertEqual(needle_mm("4,5mm"), 4.5)
        self.assertEqual(needle_mm("3 mm circular needle"), 3.0)
        self.assertEqual(needle_mm("US 6 (4 mm)"), 4.0)  # metric wins

    def test_us(self):
        self.assertEqual(needle_mm("US 7"), 4.5)
        self.assertEqual(needle_mm("US #3"), 3.25)
        self.assertEqual(needle_mm("#9 US"), 5.5)
        self.assertEqual(needle_mm("US 10.5"), 6.5)
        self.assertEqual(needle_mm("US 10½"), 6.5)
        self.assertEqual(needle_mm("US 0"), 2.0)
        self.assertEqual(needle_mm("US 2.5"), 3.0)
        self.assertEqual(needle_mm("size 13"), 9.0)
        self.assertEqual(needle_mm("US 11"), 8.0)

    def test_uk_and_canadian(self):
        self.assertEqual(needle_mm("UK 9"), 3.75)
        self.assertEqual(needle_mm("UK 8"), 4.0)
        self.assertEqual(needle_mm("Canadian 8"), 4.0)
        self.assertEqual(needle_mm("UK 14"), 2.0)
        self.assertEqual(needle_mm("UK 000"), 10.0)
        self.assertEqual(needle_mm("UK 10"), 3.25)

    def test_unknown(self):
        self.assertIsNone(needle_mm(""))
        self.assertIsNone(needle_mm("a long circular needle"))
        self.assertIsNone(needle_mm("US 12"))
        self.assertIsNone(needle_mm("UK 20"))


class GaugeTests(unittest.TestCase):
    def test_per_4_inches(self):
        self.assertEqual(gauge_per_10cm(32, 4, "in"), 31.5)

    def test_per_inch(self):
        self.assertEqual(gauge_per_10cm(8, 1, "in"), 31.5)

    def test_per_10_cm(self):
        self.assertEqual(gauge_per_10cm(22, 10, "cm"), 22.0)

    def test_per_5_cm(self):
        self.assertEqual(gauge_per_10cm(11, 5, "cm"), 22.0)

    def test_bad_unit(self):
        with self.assertRaises(ValueError):
            gauge_per_10cm(22, 10, "rows")


class SmallHelperTests(unittest.TestCase):
    def test_round_pairs(self):
        self.assertEqual(round_pairs_to_rounds(27), 54)
        self.assertEqual(round_pairs_to_rounds(0), 0)

    def test_cable_lengths(self):
        cases = {16: 40, 24: 60, 32: 80, 40: 100, 47: 120, 12: 30, 60: 150, 9: 25, 8: 20, 20: 50, 29: 80}
        for inches, cm in cases.items():
            with self.subTest(inches=inches):
                self.assertEqual(cable_length_cm(inches), cm)

    def test_display_cm(self):
        cases = {4.4: "4.5", 4.0: "4", 4.2: "4", 4.75: "5", 2.25: "2.5", 9.8: "10", 9.7: "9.5", 26.67: "27",
                 26.5: "27", 10.2: "10", 120.4: "120", 0.3: "0.5"}
        for cm, want in cases.items():
            with self.subTest(cm=cm):
                self.assertEqual(display_cm(cm), want)


if __name__ == "__main__":
    unittest.main()
