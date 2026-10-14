# The guide format (draft 0.1)

A **guide** is a knitting pattern turned into structured data that the app can show one step at a time. The format is
defined in [`guide-schema.json`](guide-schema.json). A small, invented example is in
[`example-guide.json`](example-guide.json). Both are drafts for Phase 0 and will change as the test set shows what is
missing.

## Rules

1. **Copy, never compute.** Every value is a string copied exactly as the pattern writes it: "4½", "three", "65-70",
   "0", "4,5". Conversions (inches to cm, US needles to mm) and arithmetic happen later in code, never in the guide.
2. **Every value has a source.** Steps, measurements, yarns, needles and gauge carry the page and a short word-for-word
   quote. `from_picture` is true when the value was read from an image (chart, schematic, scanned page).
3. **Per-size values** use `sized_value`, with exactly one of the following:
   * `all`: the same for every size;
   * `by_size`: one entry per size, in the order of `options.sizes`. `"-"` means "does not apply to this size", and
     `null` means "the pattern gives no value";
   * `by_choice`: one `by_size` list per value of an extra choice, such as yarn weight.
   A list that has the wrong number of values is **not repaired**. Record the values as written, as far as they go,
   and add a `list_length` doubt.
4. **Step text** keeps the pattern's wording, with each per-size number replaced by a `{slot}` named in `slots`. Numbers
   that are the same for all sizes may stay in the text.
5. **Errors in the pattern are recorded as doubts,** never fixed. Doubts are written in plain English for the knitter.
6. **Options:** `options.sizes` holds every size. `options.choices` holds at most two other choices (yarn weight, colour
   version, left/right foot, closure). A one-size pattern has one size.
7. **Pieces worked more than once** use `section.instances` ("1st sleeve", "2nd sleeve"). `implied` is true when the
   pattern does not say so.
8. **Counters:** `target` says what the step counts towards: rows, rounds, repeats, a length, an absolute row number,
   or nothing. `repeat` describes repeated blocks; `includes_first` is null when the wording is ambiguous.
   `schedules` hold AT THE SAME TIME instructions, and `section.reminders` hold running ones such as buttonholes.
9. **Step types:**
   * `instruction`: do something once;
   * `rows`: a fixed number of rows or rounds;
   * `repeat`: a block repeated;
   * `measure`: work until a length;
   * `pick_up`;
   * `tick`: finishing jobs;
   * `chart`: work a chart.
10. **Ids** are short and stable: `yoke`, `yoke-3`, `y1`, `n1`.

## Reference answers (Phase 0)

Each test pattern gets a hand-checked reference guide in `testdata-private/reference/<pattern-id>.json`, which git
ignores. It comes with `<pattern-id>.notes.md` listing the hard spots and the known errors in the pattern. The model
trial and the later tests compare the app's output against these.
