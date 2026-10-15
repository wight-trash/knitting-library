# Phase 2: the stash in grams

15 October 2026. The design for Phase 2 of [PLAN.md](PLAN.md) (A8). Upgrades the app's existing inventory; nothing
parallel.

## What Mary gets

* Each yarn knows its **ball details**:
  * grams and metres per ball;
  * weight (DK, aran, DROPS group A and so on);
  * fibre;
  * recommended needle;
  * gauge.
* **Adding a yarn by photographing the ball band.** A camera button in the existing "Add yarn" form opens the phone's
  camera. The AI reads the band and fills in the form, and she checks it before saving. Yards and ounces are converted
  to metres and grams by code.
* **Stock in grams, shown as balls:** "4.3 balls · 215 g". **Bought more** adds balls. **Correct** sets what she
  actually has. Every change is kept in a history.
* **The existing screens keep working.** The app's whole-ball count (`inventory_items.quantity`) is kept up to date
  from grams, rounded down, so statistics, the home page and project start still make sense. The existing +1/−1 ball
  buttons still work, and feed the gram history.
* **Bug fix:** a yarn picture from a shop link is fetched by the server. Today the browser's request is blocked by the
  app's own security policy, without any error shown.
* **A switch:** "Stash in grams", off by default, on the Settings card that becomes **Knitting upgrades**.

Projects reserving and using yarn come in Phase 6. The history already has the reasons they need.

## Data (fork schema version 2, in `app/fork_migrations.py`)

```
yarn_specs (
  yarn_id TEXT PRIMARY KEY,           -- upstream yarns.id (no foreign key)
  grams_per_ball REAL, metres_per_ball REAL,
  weight TEXT,                        -- as the knitter or band says: "DK", "Aran", "DROPS group B", "4-ply"
  weight_category INTEGER,            -- Craft Yarn Council 0-7 when known
  fibre TEXT,
  needle_mm_min REAL, needle_mm_max REAL,
  gauge_stitches REAL, gauge_rows REAL, gauge_over_cm REAL,
  care TEXT,
  source TEXT NOT NULL DEFAULT 'manual',   -- manual, ball_band, shop_link
  updated_at TEXT NOT NULL
)
stash_ledger (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,              -- upstream inventory_items.id (type 'yarn')
  change_g REAL NOT NULL,             -- + adds, - removes
  reason TEXT NOT NULL,               -- opening, purchase, correction, ball_count, project_reserve, project_release,
                                      -- project_use, leftover
  project_session_id TEXT,            -- for Phase 6
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL DEFAULT ''
)
```

## Rules

1. **Stock (grams)** for an item = the sum of its ledger rows. **Balls** = grams ÷ grams_per_ball, shown to one
   decimal.
2. **Opening balance.** The first time an item is read with grams_per_ball known and no ledger rows, an `opening` row
   of `quantity × grams_per_ball` is written. This happens once, and it means existing stock carries over without
   anyone retyping it.
3. **Without grams_per_ball**, the item stays in whole balls, as today. The screen asks for the ball weight ("50 g?")
   to switch it to grams.
4. **After every ledger change**, `inventory_items.quantity` is set to the whole balls, rounded down.
5. **Upstream changes to the count** (the ±1 buttons, editing the quantity, project start deducting balls) call one
   fork hook. The hook adds a `ball_count` row for the difference × grams_per_ball, so the two never drift.
6. **Corrections** write the difference to the stated amount, never overwrite. The history explains every number.
7. **The stash is the household's** (upstream has no per-user stock). `created_by` records who made each change.

## Hooks in upstream files (one marked line each)

* `app/inventory/service.py`: after `adjust_inventory`, `update_inventory_item` and `create_inventory_item` commit,
  call `fork_hooks.after_quantity_change(conn, item_id, old_quantity, new_quantity, reason)`.
* `app/recipes/repository.py` `start_project`: after its deduction, the same hook.
* `app/main.py`: one more router line.

## API (`/api/stash`, needs the switch on; admin-only where noted)

| Method | Path | Does |
| --- | --- | --- |
| GET | `/api/stash/status` | `{enabled, ballband_available}` |
| GET / PUT | `/api/stash/yarns/{yarn_id}/spec` | Read or save a yarn's ball details |
| GET | `/api/stash/items` | Every yarn item with grams, balls and spec |
| GET | `/api/stash/items/{item_id}` | One item, with its ledger (newest first) |
| POST | `/api/stash/items/{item_id}/purchase` | `{balls}` or `{grams}`, optional note |
| POST | `/api/stash/items/{item_id}/correct` | `{grams}` or `{balls}`: the amount she has now |
| POST | `/api/stash/ballband` | Multipart image. Returns proposed fields with the original wording and units, converted values, and a confidence per field. Saves nothing. |
| GET | `/api/stash/image?url=` | A public image fetched by the server (validated like upstream's link import: public addresses only, at most 20 MB, image types only) |
| GET / PUT | `/api/fork/settings` | Admin: `stash_enabled`, `guides_enabled`, `guide_model` (the Phase 1 settings endpoint, extended) |

## Ball-band reading

* A model call through the app's AI settings, using the guided model (Haiku 5.5), with one photo.
* It returns fields as written (name, brand, colour name and number, dye lot, fibre, weight, ball grams, length and its
  unit, needle, gauge, care) and a confidence for each.
* Code converts yards to metres, ounces to grams, US and UK needles to mm, and gauge per 4 in to per 10 cm, using
  `guide_builder/units.py`.
* Ball-band care symbols are not read in the first version.
* Mary sees the photo beside the filled form. Low-confidence fields are marked; nothing is saved until she taps Save.

## Tests

* Backend: ledger arithmetic, the opening balance, the hook keeping both counts in step, purchases, corrections,
  conversions, image fetch validation, and the ball-band reader with a pretend model.
* Frontend: Playwright at iPad and iPhone sizes, including the camera input (a file chooser in tests).
* The ball-band reader on real photos once Jeff has sent some.
