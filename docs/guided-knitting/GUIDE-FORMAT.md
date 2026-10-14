# The guide format (0.2)

A **guide** is a knitting pattern turned into structured data that the app can show one step at a time.

The schemas are defined in code, in `app/backend/app/guide_builder/schemas.py`, and written out as JSON by
[`tools/make_schemas.py`](tools/make_schemas.py). There are three:

| Schema | Written by | What it holds |
| --- | --- | --- |
| [`guide-schema.json`](guide-schema.json) | Code | The full guide that the app shows and Mary edits |
| [`ai-outline-schema.json`](ai-outline-schema.json) | The AI | The pattern's options, materials, techniques, charts and list of sections, with numbers kept inside exact quotes |
| [`ai-section-schema.json`](ai-section-schema.json) | The AI | The steps of one section, as exact quotes |

**AI marks, code copies.** The AI never retypes a number. It quotes the pattern, and code finds the quote in the
pattern text and copies the numbers from there. A quote that cannot be found becomes a doubt.

A small invented example is in [`example-guide.json`](example-guide.json).

## Rules for the full guide

1. **Copy, never compute.** Every value is a string copied exactly as written: "4½", "three", "65-70", "0", "4,5".
   Conversions (inches to cm, US needles to mm) and arithmetic happen when the guide is shown, never in the guide.
2. **Every value has a source:** the page and a short word-for-word quote. `from_picture` marks values read from an
   image. It is set on the source, and on each value too.
3. **Per-size values** use `sized_value`, with at most one of:
   * `all`: the same for every size;
   * `by_size`: one entry per size, in `options.sizes` order. `"-"` means "not this size"; `null` means "not given";
   * `by_choice`: one `by_size` list per value of an extra choice, such as yarn weight.
   If none of the three is set, the pattern gives no value. `alt` holds the same value in a second unit, when the
   pattern gives both. A list with the wrong number of values is recorded as written, never repaired, and gets a
   `list_length` doubt.
4. **Step text** keeps the pattern's wording, with each per-size value replaced by a `{slot}` named in `slots`.
5. **Errors in the pattern are doubts, never fixed.** Each doubt says where it came from (`origin`: ai, code or
   person). The AI never raises arithmetic doubts; code checks the arithmetic.
6. **Options:** all sizes, plus at most two other choices (yarn weight, colour version, foot, closure).
7. **Pieces and repeats:**
   * `section.instances` covers a section worked more than once ("1st sleeve", "2nd sleeve"), with `implied` set when
     the pattern does not say so.
   * `pieces` cover several sections worked together more than once, with each instance tied to a choice where it
     applies (1st slipper = left foot).
8. **Counters:**
   * `target`: what the step counts towards: rows, rounds, repeats, a length (`measured_from`, `ending`), an absolute
     row (`until_row`), matching another piece, or nothing.
   * `repeat`: a repeated block, ended by a count, a row or a condition. `includes_first` and `includes_earlier_text`
     say what a total covers.
   * `schedules`: AT THE SAME TIME instructions, with their own slots, explicit row lists, stop conditions and
     checkpoints.
   * `reminders`: running instructions that span steps or sections.
   * `checkpoint`: a stated total, optionally in parts.
9. **Step types:**
   * `instruction`: do something once;
   * `rows`: a fixed number of rows or rounds;
   * `repeat`: a block repeated;
   * `measure`: work until a length;
   * `pick_up`;
   * `tick`: finishing jobs;
   * `chart`: work a chart.
   `based_on` covers "as for the front, but"; `optional` covers optional steps.
10. **Ids** are short and stable, so a project keeps its progress when a guide is edited.

## Reference answers

The 12 private test patterns have hand-checked reference guides in `testdata-private/reference/` (git-ignored). The
0.1 originals are kept in `testdata-private/reference-0.1/`. Guides are checked with
[`tools/validate_guide.py`](tools/validate_guide.py), and built guides are scored against the references with
[`tools/pipeline_trial.py`](tools/pipeline_trial.py).
