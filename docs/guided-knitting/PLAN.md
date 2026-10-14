# Guided knitting: approach and implementation plan

Version 4, 14 October 2026. Planning only: nothing described here has been built.

**What changed from version 3.** Mary's own collection (25 patterns) was analysed. All 25 are PDFs; she already
prints web patterns to PDF on her iPhone or iPad. So:
* **No Chromium** in the app. It is not needed for the core goals (A5).
* **PDF is the main way in.** Link and saved-page imports drop to "later".
* **Reading PDFs well** becomes the hard part: two-column layouts, browser-print headers and footers, and the 2 of 25
  files with no usable text.
* **Patterns often have a second choice besides size:** yarn weight, colour version, left/right foot, closure. The
  guide model now supports that.
* Jeff decided not to tell ZeetLex until the work is done.

Part A is the approach, Part B the implementation plan, Part C what is assumed. Sources are at the end.

---

# Part A: the approach

## A1. What Mary gets

1. **She adds a pattern PDF** in the app's one Add flow, as today. DROPS PDFs she printed are recognised, and get the
   extra detail the separate importer used to add (tags, categories, videos, yarns). The separate importer is retired.
2. **Make a guided version.** The app reads the pattern and builds a step-by-step guide in the background. It shows
   in the same work queue as today's text-version jobs.
3. **She checks and edits it,** Mealie-style, with doubts listed first, including errors in the pattern itself.
4. **Knit this** (the existing "Start project", upgraded):
   * she picks her size, and any other choice the pattern offers (yarn weight, colour version, foot);
   * she picks yarn from her stash, one or more strands, and sees what she needs and has;
   * needles are suggested from the pattern.
5. **She knits** in a new Knit view:
   * one step at a time, only her numbers, in cm;
   * the diagram for the step;
   * a big "Finished round 15" counter with a soft click;
   * an estimated yarn countdown.
   The existing spanner tools stay for free counting.
6. **Flexibility:** she can change size half way, run several projects of one pattern, and carry on across weeks and
   devices.
7. **Her stash** (the existing inventory, upgraded) knows grams and metres per ball. It goes down with projects and
   up with purchases. She adds yarn by photographing the ball band.

### Principles

1. **Improve, don't duplicate.** One import, one projects system, one stash, one AI engine, made better.
2. **Nothing to set up on her devices.** It works in Safari on the iPad and iPhone, and in Chrome on Jeff's Samsung
   tablet.
3. **Her numbers only, in cm, never an invented number.** Conversions are done in code, and the original is one tap
   away.
4. **Mary is in charge.** The app proposes; she confirms and edits. Errors in a pattern are shown, never silently
   fixed.
5. **The counter is the biggest thing on screen,** and no count changes on a gesture.
6. **Merge-friendly integration** (A12).

## A2. Decisions so far

| Topic | Decision |
| --- | --- |
| Philosophy | Upgrade existing features; fold the importer in; no parallel systems or separate containers |
| Counter | A tap means "I finished this round or row"; soft click |
| Who checks patterns | Mary (Jeff tests on the dev stack as admin) |
| Editing | Mary edits, Mealie-style; she can change size mid-project |
| Projects per pattern | Several allowed |
| Finished measurements | No target; the guide supports her, she decides |
| Stash | Grams and metres per ball and other details; down with projects, up with purchases |
| Yarn countdown | An estimate: "joined a new ball" plus progress. No weighing |
| Units | cm by default; patterns in inches are shown in cm |
| AI | Through the app's engine and OpenRouter; spend not a concern; no cap in the app |
| Scope | Knitting only, from any source |
| Chromium | Not included: Mary's patterns are all PDFs (A5) |
| ZeetLex | Not told until the work is done |

## A3. How knitting patterns are put together

Most patterns have three layers:
1. **Front matter:** sizes, size guide, yarn, needles, gauge, abbreviations.
2. **Named techniques and charts.**
3. **Construction sections** in working order.

Typical sections: a top-down jumper goes neck, yoke, divide, body, sleeves (twice), neckband. Pieces go back, fronts
(mirrored), sleeves (twice), making up. Socks go cuff to toe, or toe to cuff, worked twice.

| Instruction | How the guide represents it |
| --- | --- |
| "Rounds 1-2 a total of 9-13-16 times" | **Repeat step:** "Round 2 of 2", "Repeat 5 of 13" |
| "Until it measures 30 cm" | **Measure step:** a counter with no target, an estimate from gauge, an "It measures 30 cm" button |
| "AT THE SAME TIME decrease every 4 cm, 3 times" | **Linked schedule:** "Decreases ●●○○, next on round 18", with a banner on the due round |
| Buttonholes every 8 cm, I-cord band "as before" | **Running reminder** across steps or sections |
| "Until row 24", "increase on rows 8, 16, 24" (absolute row numbers) | **Row-numbered steps**, counting from the piece's start |
| Sleeves, socks, fronts, left and right foot | **Separate steps**, even when the pattern only implies the second |
| A value of 0 or "-" for some sizes | The step is **hidden for those sizes** |
| "Increase 18 stitches evenly" | **Spacing worked out in code** for her size |
| A chart per size group, or "start at the arrow for your size" | The step links to **her chart** and start point |
| "Row 2 and all WS rows: purl" | Expanded into explicit rows |
| "Read DECREASE TIP", "FRinc", "patt2tog" | **Links** to the technique or abbreviation |
| Pick up, cast off, seams, blocking | **Tick-off steps** |
| "= 164 sts" | **Checkpoint:** "You should now have 164 stitches" |
| Instructions living outside the PDF (a "Sock Guide" web page, videos) | **Links** kept, marked "outside the pattern" |

## A4. What Mary's patterns showed

**The collection: 25 PDFs, nothing else, knitting only.**

| Kind of PDF | Count | Notes |
| --- | --- | --- |
| Designer-made (Google Docs, InDesign, Canva, Word, Affinity, CorelDRAW) | 21 | Hobbii (7), Berroco, Manos del Uruguay, PetiteKnit, Tin Can Knits, West Yorkshire Spinners and others |
| Printed from a web page in Safari (DROPS) | 2 | URL, date and "Page x of y" inserted mid-text |
| No usable text: words turned into shapes | 1 | Milano Zip-up |
| No usable text: scanned paper leaflet | 1 | Patons striped sweater |

Six are translations (Norwegian, Spanish, Danish, Finnish), which shows in the wording. Assessed difficulty: 12
straightforward, 7 moderate, 6 hard.

**Reading the text**
* **Two-column layouts** interleave in plain text extraction: one section's text mixes into another. Canva files come
  out in a scrambled order. The fix is to read text with its position on the page, and rebuild the columns in code.
  The AI also sees the page images.
* **Plain extraction deletes line-end hyphens** and merges numbers in DROPS lists ("176-192212-232"), beyond repair.
  Layout mode with a rejoin rule is needed. That rule must allow for spaces around a size Mary had highlighted when
  printing.
* **Text-coverage check on every page.** Two files have no real text. One is a scan inside a cover page that does
  have text, so a check on the whole document would miss it. Pages without text go to the picture-reading route.
* **Clutter to strip:**
  * browser headers and footers;
  * "Powered by TCPDF" and SKU lines (Hobbii);
  * marketing pages;
  * photo captions.
* **Character problems:** ligatures (ﬁ), zero-width spaces, icon glyphs read as "?", curly quotes used as inch marks,
  and decimal commas ("4,5 mm").
* **Links in annotations:** some videos and guides exist only as PDF link annotations. These are read and kept.

**Sizes and other choices**
* **Size notations seen:**
  * "1 (2) 3 (4)": alternate brackets, each number one size, sometimes nested;
  * "(a, b, c) [d, e, f] {g, h, i}" with "X" for "not this size";
  * "40 [44:48:52]";
  * "XS 82, S 86";
  * "every 9. (8.) 7. row";
  * "p (k) p (k)";
  * ranges as values ("65–70 (75–80)").
  One file uses three notations; one marks larger sizes only by font colour, which text extraction loses.
* **Brackets do not always mean sizes.** They can be a unit conversion ("US 2.5 (3 mm)", "[40¼ in]").
* **A second choice besides size:**
  * yarn weight: the Tin Can Knits mittens and the Cozy Fit pullover come in four weights;
  * colour version: Hobbii Dorthea and Thekla;
  * left or right foot: Sailor Slippers;
  * closure type: Barcelona.
* **Made-to-measure:** Barcelona's stitch counts are spreadsheet placeholders ([A], [G-1]) with no numbers in the PDF.

**Units and needles**
* inches first or cm first, or both;
* gauge per inch, and before and after felting;
* US, UK/Canadian and mm needle sizes, where UK/Canadian numbers run the opposite way to metric;
* "cms", "mts", untranslated labels.

**Errors in published patterns.** These make the checker's best tests:
* **Azulejo:** a 10-value list for 9 sizes; increases that compute to 27 against 26 stated.
* **Thekla:** a 7-value list for 8 sizes; a total that counts one shoulder only.
* **Scrunchie bag:** its row guide and photo guide disagree.
* **Petrona:** shoulder counts disagree.
* **Dartmoor:** 44 where 45 is implied.
* **Balaclava:** an impossible "6 left" (40, 20, 10, 5).

The two DROPS prints check out completely, which makes them good controls against false alarms.

**Charts:** mostly raster images, some small (230 to 300 px), some vector with grid numbers as text. One file has a
chart per size; several have no written version.

**Also tested from earlier:** DROPS Lavender Harvest and Lucky Wish PDFs, the Purl Soho hat (inches, yards, US
needles), and two saved web pages (Prima cardigan, imknitting vest).

## A5. The upgraded import, and why no Chromium

**PDF is the way in,** through the app's existing Add flow (`ImportWizard`). That already handles PDFs, duplicates,
page images and thumbnails.

**DROPS PDFs are recognised** from the garnstudio address printed on each page. The importer's DROPS readers, moved
into the app, then add tags, categories, videos and yarns:
* parsed from the PDF text;
* plus the pattern's web page if DROPS allows the request;
* polite fetching only: one request at a time, an honest identity, and a refusal reported, never worked around.

**Why Chromium is not included.** It was only ever needed to turn a web page into a PDF. Against the core goals:
* **Mary's patterns are all PDFs already.** She prints web patterns on her own devices.
* **The guide does not need a PDF.** It is built from text and images.
* **The cost is real.**
  * The library image is 157 MB compressed; Chromium on Alpine adds a 125 MB download and 276 MB installed, before
    its libraries, roughly doubling the image.
  * It would put a full browser engine, rendering internet pages, inside the main app container next to Mary's data.
  * Playwright has no Alpine build, so the importer's PDF code would not carry over as it is.

**Later, if ever wanted:** "From a link" and "Saved web page" options can be added without Chromium. They would keep
the page's text and pictures (no PDF). They are in Phase 9.

**Retiring the importer:** when the app passes the importer's own tests, the "Import from DROPS" link points at the
Add flow, and `knit-import` leaves the compose files. Its tests move with its code.

## A6. Building a guide from any pattern

```
PDF ─► 1 Read ─► 2 AI builds the guide ─► 3 Code checks ─► 4 Mary reviews ─► ready
DROPS PDF ─► DROPS readers (no AI) ─────────►┘
```

### 1. Read

* **Text with its position on each page,** columns rebuilt in reading order. Plus layout-mode text with the hyphen
  rejoin, for DROPS-style lists. The tool is chosen in Phase 0: poppler's own bounding-box output or a permissively
  licensed PDF library.
* **Page images** at a resolution the AI can read charts from.
* **Text coverage per page:** pages without real text are flagged for picture reading.
* **Clutter stripped:** headers, footers, stamps, marketing pages, captions.
* **Characters normalised** (ligatures, zero-width spaces, decimal commas), with the originals kept.
* **Link annotations** read.

### 2. AI builds the guide

* Text and page images go to the chosen model, which returns fixed JSON.
* Every step quotes its source text and gives its page.
* The AI labels units and size notation; it does not convert or compute.
* Pages without text are read from the image and marked "from the picture, please check".

### 3. Code checks

Anything doubtful goes on Mary's list:
* every number appears in the source;
* every per-size list has one value per size (and per other choice), or is marked "all sizes";
* stitch counts add up where stated;
* duplicate instructions agree with each other (row guide against photo guide, chart against written rounds);
* abbreviations are defined;
* the guide covers the whole pattern;
* repeat counts whose meaning is ambiguous ("10 times" including the first, or not) are flagged.

Conversions to cm, metres, grams and mm happen here, with the originals kept. Even spacing is worked out per size.

### 4. Mary reviews

Doubts first (A9).

### While a guide is being built (Jeff, 15 October)

Building runs on the server as a background job, so the iPad sleeping, Safari closing or the app being switched does
not stop it. The pattern page shows **live progress** at every stage:
* reading;
* pictures, page by page;
* outline;
* each section by name;
* checks;
* repair.

The page:
* asks for the latest progress the moment it becomes visible again, so after unlocking it is up to date at once;
* shows an elapsed time that keeps counting;
* never sits still: the builder repeats its latest event every few seconds while a model call is running.

No notifications. A page that looked frozen would make Mary cancel, so "frozen-looking" counts as a bug.

**Made-to-measure patterns** (Barcelona): the guide is built with the placeholders shown as "your number". Mary
types her numbers in once, in the editor. Full spreadsheet support is not planned.

## A7. Sizes and other choices

* **Options:** a pattern has a size list plus up to two further option lists, for example yarn weight and colour
  version. Every per-size value can depend on these. Mary picks each once at the start.
* **The size guide** is shown as the pattern gives it: a table, or the image (marked "check against the picture"
  where AI read it). Her column is highlighted.
* **Changing size or another option mid-project:**
  * progress is kept;
  * targets switch to the new choice;
  * steps past their new target show in amber;
  * the yarn estimate recalculates;
  * the change goes into the project history.

## A8. Stash and yarn (the existing inventory, upgraded)

* **Yarn details**, added beside today's free-text fields:
  * grams and metres per ball;
  * weight group (DROPS A-F, CYC 0-7, UK/US name);
  * fibre;
  * needle in mm;
  * gauge.
* **Adding yarn by photographing the ball band.** A camera button in the existing Add yarn form opens the phone's own
  camera; nothing to install. AI fills in the details and Mary checks them.
* **Bug fix:** a yarn's picture from a shop link fails today. The app's own security policy blocks it, and no error
  is shown. The picture will be fetched on the server instead.
* **Stock in grams:**
  * purchases add, projects draw down, corrections adjust;
  * shown as balls, "4.3 × 50 g";
  * the existing skein count is derived from grams, so existing screens and statistics keep working.
* **In a project:**
  * yarn is reserved at the start, per strand;
  * a shortfall is amber, never blocking;
  * usage is estimated: one tap on "Joined a new ball", plus each step's share of the pattern's grams, worked out
    from its stitch counts;
  * **second sleeve:** what the first sleeve took predicts the second ("1st sleeve used about 1.3 balls; you have 2.4
    left");
  * at the finish, used yarn leaves the stash and leftovers stay.

## A9. Mary as the editor

* **The review screen:** the guide and the pattern page side by side on iPad landscape, tabs on portrait and iPhone.
  Doubts first: "Yarn amount missing for size XXL", "Row guide and photo guide disagree on row 24", "Read from the
  picture, please check".
* **Editing a step:** text, type, targets per size, checkpoint, linked page or chart, notes. Split, merge, reorder,
  add, delete.
* **Edits change the pattern's guide** for future projects. Running projects keep their progress, because steps have
  stable identities.
* **Project notes** stay with the project.
* **The original wording** is one tap away. Rebuilding from the pattern asks before replacing her edits.

## A10. The screens

**Layout** follows the available width:
* two panes from 1000 px;
* stacked from 600 px;
* single column below 600 px.

**The Knit view** is a new tab beside Original, Text version and Review.

**Step card rules:**
* her numbers in bold on a pale accent, never colour alone;
* tap a number for all sizes and the original wording;
* a big "Finished round 15" button above "Round 15 · 14 done";
* a separate Undo button, plus a six-second "Recorded · Undo" message;
* each tap saved as its own record, so two devices cannot overwrite each other, with offline taps queued;
* no gestures change a count;
* lap protection and a lock mode;
* "Set to…" and "Rip back";
* targets never auto-advance;
* overshooting shown in amber.

**The click** respects the silent switch by default. An opt-in setting plays it anyway, but that pauses music.

**The screen stays awake** while knitting, released after about 45 minutes without a tap.

### Knit view, iPad landscape (illustrative numbers)

```
+--------------------------------------------------------------------------------+
| < Close   Lucky Wish · size L · project 1              Yarn ▮▮▮▯ ~6 balls  Aa ☾ |
+----------------+------------------------------------------+--------------------+
| SECTIONS       |  SLEEVE 1 · step 2 of 5                   |  CHART A.1  [⤢]    |
| ✓ Yoke    7/7  |  Work in stocking stitch until the sleeve |  +--------------+  |
| ✓ Body    5/5  |  measures [38 cm] from the division.      |  | chart image, |  |
| ● Sleeve 1     |  AT THE SAME TIME dec [2] sts every       |  |  pinch zoom  |  |
|   1 ✓ Pick up  |  [3½ cm], [7] times.     (all sizes ▾)    |  +--------------+  |
|   2 ● Shaping ◀|  Decreases ●●●○○○○  next at about 21 cm   |  [Abbr][Tips]     |
| ○ Sleeve 2     |  You should then have 52 stitches          |  [Gauge][Notes]   |
| ○ Neck         |  [ Joined a new ball ]                     |                    |
|                |  < Previous step           Next step >    |                    |
+----------------+------------------------------------------+--------------------+
|  Round 41 · 40 done · about 44 rounds to 38 cm         [ ↶ Undo ] [ FINISHED ROUND 41 ] |
+--------------------------------------------------------------------------------+
```

### Setup: size, options and yarn (illustrative numbers)

```
+-----------------------------------------------------------------+
| Choose your options    Size guide from the pattern  [⤢]          |
| Size:        S      M     [L]     XL    XXL   XXXL               |
| Chest       96    104   [112]   124   136   148  cm  (picture)   |
| Yarn weight: ( fingering ) ( sport ) (● DK ) ( worsted )          |
|                                              [ Continue ]        |
+-----------------------------------------------------------------+
| Yarn for size L, DK                                             |
| Strand 1: [ West Yorkshire Spinners DK, Teal ▾ ]  You have 6 balls ✓ |
|  + Add a strand                                                  |
| Needles: 3.5 mm and 4 mm                          [ change ]      |
|                          [ Start anyway ]   [ Start project ]     |
+-----------------------------------------------------------------+
```

### Review and edit (iPad landscape, illustrative)

```
+--------------------------------------------------------------------------------+
| < Back   Check the guide: Thekla                3 things to check   [ Done ]   |
+---------------------------------------+----------------------------------------+
| ⚠ Neck list has 7 values for 8 sizes   |  PATTERN p.3                           |
| ⚠ Total says 198; shoulders add to 216 |  (page image, quoted text highlighted) |
| ⚠ Chart read from the picture: check   |                                        |
|---------------------------------------|                                        |
| YOKE                                  |                                        |
|  1 Cast on 96 (104) 112 (120)... sts ✎|                                        |
|  2 Rib 6 rounds                   ✎   |                                        |
| [ + Add step ]  [ Split ]  [ Merge ]   |                                        |
+---------------------------------------+----------------------------------------+
```

## A11. AI in the app

**Upgrade the existing AI engine** rather than add a second one. Guide building and ball-band reading become new job
types in the existing queue and work-queue dock, on the same settings page. The engine gains:
* fixed JSON output;
* several pages per call, with the text;
* retries;
* cost recorded per call;
* a model per job type;
* cancelling between calls;
* privacy fields on every request.

Two existing bugs are fixed on the way: token usage of queued jobs is thrown away, and pages beyond the limit are
silently dropped.

**Features, ranked:**
1. Build a guide from any pattern (core), including picture reading for pages without text.
2. Add yarn from a ball-band photo.
3. "What does this step mean?", answered only from the pattern.
4. Read a size guide, chart start points and chart arrows from pictures, always confirmed.
5. Later: translation, purchases from receipts.
6. Not yet: charts into written rows.

**Code, not AI:** units, sizes, arithmetic, spacing, yarn maths.

**Cost:** OpenRouter prices checked on 14 October 2026:

Measured in Phase 0 with Claude Haiku 5.5 ($0.10 in and $0.50 out per million tokens): the pipeline costs **1 to 3.5
US cents per pattern**. The earlier estimates in this section assumed about 4,000 output tokens per guide; the single
call actually wrote about 40,000. Sonnet and Opus are ruled out on cost.

* Mary's 25 patterns average about 8 pages, so building all of them once costs a few dollars at most.
* The model is chosen after the Phase 0 trial.
* Running a model on the NAS is not practical.

## A12. Integration and the upstream cost

| Part | Existing files extended | New files | Conflict risk |
| --- | --- | --- | --- |
| Importer folded in, DROPS PDFs recognised | `ImportWizard.jsx` (one call after saving), `AppShell.jsx` (repoint the fork's link) | `app/patterns/` (ported readers, with tests) | Low to medium |
| PDF reading and guide building | `ai/jobs.py` (job types, the two fixes), `RecipeViewer.jsx` (Knit tab) | `app/guide/`, `GuideView.jsx`, `GuideEditor.jsx` | Medium |
| Projects: options, strands, steps, several active | `recipes/repository.py` (two guards, hooks), `ProjectStatus.jsx` (start dialog), `RecipeCard.jsx`, `HomePage.jsx` | side tables keyed by project session; `ProjectSetup.jsx`, `YarnCountdown.jsx` | High |
| Stash in grams with yarn details | `inventory/service.py`, `stats/service.py`, `InventoryPage.jsx`, `YarnUploadModal.jsx`, `YarnViewer.jsx`, `StatisticsPage.jsx` | `yarn_specs`, `stash_ledger` side tables; `YarnSpecFields.jsx`, `BallBandCapture.jsx` | Medium |

**Merge-friendly techniques:**
* logic in new packages, each with its own router;
* a fork migration module, so upstream's schema code is never edited;
* side tables, not wider upstream tables;
* one-line hooks inside upstream functions;
* new components mounted with one line each, and calls in `utils/forkApi.js`;
* fields added, never renamed or removed;
* strings in a fork locale file;
* the weekly upstream check and `sync-upstream.sh --check`.

**The cost:** real edits in about a dozen upstream files. Upstream has slowed sharply (92 commits in June, 6 in
September, none so far in October), and most of those files have not changed upstream since July.

## A13. Bugs found on the way

| Bug | Plan |
| --- | --- |
| Yarn shop-link import cannot load the picture (security policy, no error shown) | Fix |
| AI engine discards token usage of queued jobs | Fix |
| AI engine silently drops pages beyond its limit | Fix |
| The tag fix, bcrypt 5's 72-byte limit, the metadata-only locale check, `tesseract` not installed | Note; upstream contact deferred |
| Staged imports may show in the recipe list before confirmation | Check (unverified) |

## A14. Risks

* **The AI gets a pattern wrong.** Guards: quotes, checks, Mary's review, and the model trial.
* **Errors in patterns.** Shown, not fixed.
* **Scrambled layouts.** Position-based reading plus page images; tested on the two-column and Canva files.
* **No text layer.** Picture reading, marked for checking.
* **Second choices and made-to-measure patterns.** The options model and the placeholders.
* **Upstream conflicts.** A12.
* **Apple devices.** Playwright's WebKit engine for automation; Mary's iPad on dev for real.
* **Size of the work.** Phased, behind switches.

---

# Part B: implementation plan

Each phase ends with something to try on the dev stack. Parts go live behind their own switch when ready.

## Phase 0: test set, reading tool and model trial

**Status: done, 15 October 2026.** Results:
* **Test set:** 12 patterns with hand-checked reference guides (private). They found real errors in 7 of the
  patterns, and confirmed the DROPS arithmetic.
* **Reading tool:** poppler word positions plus our own reading order ([phase0-pdf-reading.md](phase0-pdf-reading.md)).
* **Model:** Claude Haiku 5.5 through OpenRouter. Jeff ruled out Sonnet and Opus on cost; Qwen 3.8 Flash was tried
  and was slower and less reliable.
* **Format:** 0.2 ([GUIDE-FORMAT.md](GUIDE-FORMAT.md)).
* **Pipeline:** built ahead of plan, in `app/backend/app/guide_builder/` (Phase 4's engine, not yet used by any
  screen).

Second full run, against a single call:

| | Single call | Pipeline |
| --- | --- | --- |
| Time, 12 patterns | 35 min | 9.6 min |
| Cost, 12 patterns | $0.31 | $0.20 |
| Valid guides | 9 of 12 | 12 of 12 |
| Longest gap between progress updates | none sent | 3 s |
| Per-size values found | 0.84 | 0.79 |
| Per-size values correct | 0.94 | 0.91 |

Accuracy work is parked for now: the scanned and Canva patterns, and values that depend on yarn weight. Ideas are
in the commit history (1d8d162).


**Test set**, kept private and never committed:

| Pattern | Tests |
| --- | --- |
| DROPS Wisteria Glow and Cocoa Beach (Mary's Safari prints) | Browser-print clutter, the highlighted-size trap, controls with clean arithmetic |
| DROPS Lavender Harvest and Lucky Wish (Jeff's PDFs) | Hyphen loss, chart per size group, arrow-triggered steps, implied second sleeve, zero values, two strands |
| Azulejo (Hobbii) | Alternate brackets, list-length and arithmetic errors, raster charts with start points |
| Thekla (Hobbii) | Colour versions, a list one short, a wrong total |
| Sailor Slippers (Canva) | Scrambled order, left and right foot side by side, felting gauge |
| Cozy Fit pullover | Yarn weight × size, sentences split by number blocks |
| Scrunchie bag | Two guides that disagree, absolute row numbers |
| Milano Zip-up | No text layer (outlined), ranges in lists, links only in annotations |
| Patons striped sweater | Scan inside a text cover, inches with [cm], Canadian needle numbers |
| Purl Soho hat | Inches, yards, US needles, "round pairs" |

**Steps:**
1. **Write the expected guide by hand for each.** These become the reference answers.
2. **Choose the PDF reading tool:** poppler bounding boxes or a permissively licensed library. Judge it on the
   two-column and Canva files.
3. **Model trial:** three or four models on the set, compared for accuracy, cost and time. Choose the defaults.

## Phase 1: foundations

* `app/fork_migrations.py`, `fork_hooks`, `utils/forkApi.js`, a fork locale file, and feature switches.
* The AI engine upgrade and its two fixes.
* A fork-only CI workflow that runs the library's backend tests plus the new tests on every push and pull request.

## Phase 2: the stash upgrade

* Yarn details, grams, purchases and corrections, with the skein count derived.
* Ball-band capture.
* The picture fix.
* Statistics and the Inventory page in grams and balls.
* **First live release** behind its switch.

## Phase 3: the import upgrade (importer folded in)

* Port the importer's DROPS readers and checks into `app/patterns/`, with their tests.
* Recognise DROPS PDFs and add the DROPS extras.
* Repoint "Import from DROPS". Retire `knit-import` once the importer's tests pass in the app.

## Phase 4: reading PDFs and building guides

* Position-based reading, layout text with the hyphen rejoin, the coverage check, clutter stripping, character
  normalisation, link annotations.
* The AI guide job, with picture reading. The DROPS path.
* The checks and conversions. The options model. Made-to-measure placeholders.
* Tests: every Phase 0 pattern against its reference answer, every published error caught, and the DROPS controls
  raising no false alarms. Unit tests for every notation trap in A4.

## Phase 5: review and edit

* The review screen and step editor, with history.
* Mary tries it on her iPad on dev.

## Phase 6: the projects upgrade

* The start dialog with size, options, strands and needles.
* Several active projects per pattern.
* Changing size or options mid-project.

## Phase 7: the Knit view

* The step card and counter rules.
* All step types, including running reminders and row-numbered steps.
* The yarn countdown and the second-sleeve prediction.
* Navigation and resume, reference, "what does this step mean?".
* Comfort settings.
* Playwright WebKit tests at iPad and iPhone sizes, plus a two-device test.

## Phase 8: Mary uses it

* One real project on dev; fix what confuses her.
* Then live behind switches, with a snapshot first.
* Update the guide, `FORK.md` and the in-app help.

## Phase 9: later, each its own decision

* "From a link" and "Saved web page" imports (no Chromium).
* Translation; purchases from receipts.
* Cropped diagrams per step; chart row highlighting.
* Offer the work to ZeetLex.

## How the work is run

* On `dev`, with image checks and the dev stack.
* Sub-agents for big research and analysis.
* Tests first for reading, parsing and checks.
* The guide and this plan updated at the end of each session.

---

# Part C: assumed unless Jeff says otherwise

1. Mary's edits improve the pattern's guide for every future project.
2. Yarn is reserved when a project starts, drawn down while knitting, and leftovers return at the finish.
3. Made-to-measure patterns (like Barcelona) are supported by Mary typing her numbers in, not by spreadsheet support.
4. Up to two choices besides size per pattern (for example yarn weight and colour version) is enough.

---

## Sources

* DROPS lessons and yarn groups: https://www.garnstudio.com/lesson.php?id=24 and
  https://garnstudio.com/yarn-groups.php?cid=19
* Craft Yarn Council, sizing: https://craftyarncouncil.com/standards/body-sizing
* Tin Can Knits, multi-size instructions: https://blog.tincanknits.com/2020/10/08/reading-multi-size-knitting-pattern-instructions/
* Interweave, AT THE SAME TIME: https://www.interweave.com/article/knitting/mastering-time-instructions
* Yarn weights and substitution: https://www.lovecrafts.com/en-gb/c/article/yarn-weights-translated and
  https://hobbii.com/blog/how-to-calculate-substitute-yarn-amounts
* knitCompanion and Ribblr: https://apps.apple.com/us/app/knitcompanion-knitting-more/id1058142783 and
  https://ribblr.com/learn/how-to-use-ribblr-epattern
* OpenRouter (prices checked 14 Oct 2026): https://openrouter.ai/api/v1/models,
  https://openrouter.ai/docs/guides/features/structured-outputs,
  https://openrouter.ai/docs/guides/privacy/data-collection
* Alpine chromium package (sizes checked 14 Oct 2026): https://pkgs.alpinelinux.org/package/v3.23/community/x86_64/chromium
* NAS hardware: https://www.starryhope.com/nas/models/ugreen-nasync-dxp6800-pro/
* Apple HIG: https://developer.apple.com/design/human-interface-guidelines/accessibility
* Screen Wake Lock: https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API
* Audio session and the silent switch: https://developer.mozilla.org/docs/Web/API/AudioSession/type
