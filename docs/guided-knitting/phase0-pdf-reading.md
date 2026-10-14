# Phase 0: reading pattern PDFs

14 October 2026. Which way to get pattern text in reading order (PLAN A4). The prototype is
[`tools/readpdf.py`](tools/readpdf.py). The evaluation harness quotes the private test patterns, so it is kept in
`testdata-private/tools/pdf_reading_evaluate.py` (git-ignored).

## Method

16 PDFs: `testdata-private/patterns/` plus DK sock, See My Vest, Petrona and Fraile.
* **Order:** 20 hard pages, checked by eye against `pdftoppm` renders. Each has 6 to 14 phrases in true reading
  order; a page passes if all appear in that order. 13 pages were used for tuning. Of 7 added later, 4 passed first
  time, 2 were fixed afterwards and 1 still fails.
* **DROPS:** 14 number runs broken at a line end, from `-layout` output. Every approach gets the same rejoin rule.

## Candidates

| Approach | Licence | python:3.14-alpine | Speed | Order (13 + 7) | DROPS |
| --- | --- | --- | --- | --- | --- |
| 1. `pdftotext -bbox-layout` + our ordering | Poppler run as a program; our code | Nothing new | 0.29 s/file | **13/13, 6/7** | **14/14** |
| 2. pdfplumber | MIT | Pure Python; dependencies have musllinux cp314 wheels; about 30 MB plus Pillow | 2.3 s | 1/13, 1/7 | 14/14 |
| 2b. pdfplumber words + our ordering | MIT | as above | 2.6 s | 10/13, 4/7 | 14/14 |
| 3. pypdfium2 | Apache-2.0 or BSD-3 | musllinux wheel, 13 MB | 0.05 s | 4/13, 2/7 | 14/14 |
| 4. pdfminer.six (LAParams) | MIT | Pure Python plus wheels, 26 MB | 1.8 s | 2/13, 1/7 | 14/14 |
| `pdftotext` (today) | | | 0.09 s | 1/13, 0/7 | 5/14 |
| `pdftotext -layout` | | | 0.09 s | 1/13, 1/7 | 14/14 |

Installs were checked with uv, binary-only, for musl cp314: none needs a compiler. PyMuPDF (AGPL) was excluded.
* pdfplumber loses spaces on Affinity and Google Docs files ("dk:22stsand30rnds").
* pdfminer's layout analysis fixed two pages but broke Canva and grid pages.
* pypdfium2 gives content-stream order: fast, keeps hyphens, no layout analysis.
* Only approach 1 strips clutter (0 lines left, 75 in the rest); that step works with any word source.

## Hard cases with approach 1

| Case | Result |
| --- | --- |
| DK sock, Petrona, Cozy Fit (two columns) | Correct, including superscripts ("1st size") |
| See My Vest (two-column block under one column) | Correct |
| Fraile, Sailor Slippers (Canva) | Correct; text beside a size table correct; photo captions read row by row |
| DROPS (4 files) | 14/14 runs intact; highlighted sizes keep their spaces ("16-17- 18 -19") |
| Browser lines, TCPDF, SKU | All removed; no other text lost on any page |
| Ligatures, zero-width spaces | Normalised (Fraile, Petrona, Thekla) |
| Milano (outlined text) | All 13 pages flagged (0 to 11 characters each) |
| Patons (scan inside a text cover) | All 5 pages flagged, page by page |
| Failure | Arched advert lettering (DK sock page 2) garbled; rotated labels backwards |

The coverage check also flags 15 cover and photo pages elsewhere; harmless, they go to picture reading.

**Links:** pypdf (BSD-3, pure Python, 1.8 MB) read all 83 link annotations with rectangles, so the words under each
link can be kept. `pdfinfo -url` finds the same 83 without rectangles and needs no new package.

## Recommendation

**Approach 1**, plus pypdf for links. It alone read the two-column and Canva pages correctly, adds no native
dependency and is fast. The ordering only needs word boxes, so pypdfium2 could replace poppler later.

Risks: thresholds are tuned on 16 files, so add tests built from synthetic word-box fixtures (the PDFs are
private). The coverage render takes up to 6 s on photo-heavy files: reuse the page images made for the AI.

## Algorithm outline

1. **Words:** `pdftotext -bbox-layout -enc UTF-8`; drop the DOCTYPE, parse with ElementTree. Ignore poppler's
   blocks: their order is wrong on Canva and re-saved files.
2. **Segments:** take words left to right; join a word to a segment on the same baseline (half-height overlap)
   less than one line height away. Rotated words stay alone. No space where words touch.
3. **Clutter:** top or bottom 7.5%: lines up to 90 characters with a URL, a `dd/mm/yyyy` date, or a lone page
   number. Top or bottom 12%: lines with letters repeating (digits ignored) on over half the pages. Anywhere:
   "Powered by TCPDF". Keep what was removed.
4. **Tables:** 2+ stacked rows of 3+ cells (up to 25 characters), plus headers just above, become one box that is
   never split and is read row by row.
5. **Columns:** try each x across the middle half, in clear space. Segments crossing x are full-width rows that cut
   bands. A band is two columns when each side has 2+ segments, is 60 pt and 20% wide, and they overlap
   vertically; and either both sides are running text (40% of characters in segments 40% of the side's width)
   and not a short table, or one side is text and under half its rows line up with the other. Pick the x with
   most segments in column bands, centred in its run. Read left then right, recursively; re-order the remaining
   rows together. No gutter: split at full-width gaps of 2.5 line heights, else top to bottom.
6. **Lines:** join a line ending "digit-" to a next line starting with a digit, without a space.
7. **Characters:** ligatures to letters; drop zero-width characters and soft hyphens; odd spaces to spaces. Keep
   decimal commas for the number checker.
8. **Coverage:** under 150 non-space characters on a page means picture reading; ink share spots blank pages.
9. **Links:** for each `/Link` with a `/URI`: page, URL, rectangle, words under it.
