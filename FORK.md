# This fork

This is `wight-trash/knitting-library`, a fork of [ZeetLex/knitting-library](https://github.com/ZeetLex/knitting-library).

The `jeff` branch is upstream `main` plus a few things on top.

| Where | What |
| --- | --- |
| Link patch commit | Makes `[label](https://...)` links clickable in the old (`MarkdownView`) text version viewer. Upstream's new reader (1.0.0+) already does this for `gfm-v1` text versions. |
| Nav patch commit | Adds an "Import from DROPS" link to the sidebar and the Add menu. It goes to `/import/`, where the importer is served. Only `AppShell.jsx`, `AppShell.css` and `en.js` change. |
| `importer/` | The importer, a separate app that adds patterns from websites to Knitting Library. Own README. |
| `deploy/docker-compose.yml` | The live stack: both apps on one private network. |
| `deploy/docker-compose.dev.yml` | A test copy of the stack, built from `dev`. Runs beside the live one. |
| `.github/workflows/` | Image builds for both apps, and a weekly upstream check. |
| `sync-upstream.sh` | Keeps the `jeff` branch in step with upstream. |

The two patch commits above touch upstream files, and so do the small `fork`-marked edits listed under
"Guided knitting". Everything else is new files, so it cannot conflict with upstream.

## Branches

| Branch | What | Images |
| --- | --- | --- |
| `main` | A plain copy of upstream. Never commit here. | none |
| `jeff` | Live. Upstream `main` plus the patches. The NAS runs this. | `knitting-library:jeff`, `knit-import:latest` |
| `dev` | Testing. `jeff` plus work not yet proven. | `knitting-library:dev`, `knit-import:dev` |

Every image also gets a `sha-<commit>` tag, for rollback.

Work goes on `dev` first. Pushing to `dev` builds only the `:dev` images, so the live stack is not touched.
Try it on the dev stack (`deploy/docker-compose.dev.yml`), then promote it:

```
git checkout dev && git rebase jeff        # only needed if jeff has moved since dev was made
git push --force-with-lease origin dev     # only if the rebase changed anything
git push origin dev:jeff                   # jeff moves to dev; the live images rebuild
```

`git push origin dev:jeff` is refused unless `dev` is `jeff` plus new commits on top. That is the safety
check: it cannot overwrite anything on `jeff`. After an upstream sync of `jeff`, rebase `dev` onto `jeff`
in the same way.

## Keeping in step with upstream

Cheap, as far as the history shows. These are estimates, not promises.

* The nav link patch adds an item to two menus in `AppShell.jsx`, a file upstream edits often. It is the most likely patch to need a hand fix.
* The link patch touches the last lines of `MarkdownView`, a small part of a very large file.
* The Guided tab is the edit most likely to conflict: upstream rewrote the view tabs in 1.0.0 (see "Guided tab and upstream's view tabs" below).
* Upstream is slowing down: about 77 commits in June, about 10 in September.
* Upstream tags releases in git (`1.0.0`, `1.0.1`) but publishes only `latest`, `beta` and `0.9.1` on Docker Hub, so a Docker version tag cannot be relied on. The image built here is pinned to a commit.

Expect a few minutes a month. Most months nothing needs doing.

```
./sync-upstream.sh --check     # how far behind, and would the rebase be clean
./sync-upstream.sh             # rebase onto upstream main
git push --force-with-lease origin jeff
```

The weekly workflow (Mondays, on `jeff`, the default branch) runs the check and fails if the rebase would conflict. GitHub emails you about failed runs. The push builds new images. Then update the stack in Arcane.

If a rebase stops on a conflict, git names the file. Keep upstream's new code, put the patch's lines back, then `git add` and `git rebase --continue`.

## Guided knitting (in progress)

Plan: [`docs/guided-knitting/PLAN.md`](docs/guided-knitting/PLAN.md). Everything is behind a switch that is off by
default (Settings, Knitting upgrades), so the live library looks the same until it is turned on.

| Where | What |
| --- | --- |
| `app/backend/app/guide_builder/` | Builds a guide from a pattern PDF: reading, AI outline and sections, numbers copied from the pattern, checks, progress events. No app dependencies. |
| `app/backend/app/guided/` | The app side: settings (`fork_*` rows in `app_settings`), background builds that survive restarts, `/api/guided/...` |
| `app/backend/app/fork_migrations.py` | The fork's own tables (`guide_jobs`, `guides`; version 2: `yarn_specs`, `stash_ledger`) and schema version; upstream's schema code is not edited |
| `app/backend/app/stash/` | The stash in grams ([design](docs/guided-knitting/PHASE2-STASH.md)): ball details, gram history, ball-band reader, server-side picture fetch, `/api/stash/...` and `/api/fork/settings` |
| `app/backend/app/fork_hooks.py` | `after_quantity_change`: upstream's ball count changes feed the gram history (inside the caller's transaction; never raises). Also the upstream fixes below |
| `app/frontend/src/fork/` | The fork's own API calls, strings and screens (the Guided tab, the Knitting upgrades settings card; `stash/`: ball details, ball band photo, grams on the inventory cards, Bought more, Correct, history) |
| `.github/workflows/backend-tests.yml` | Runs all backend tests on every push and pull request |

Edits to upstream files, all marked `fork`:
* `app/backend/app/main.py`: 5 lines (guided and stash routers, start-up);
* `app/backend/app/inventory/service.py`: 3 lines, the stash hook in create, update and adjust;
* `app/backend/app/recipes/repository.py`: 5 lines, the stash hook after `start_project` deducts balls, and the
  four upstream fixes below (`list_recipes`, `delete_recipe`, `delete_project_session`, `clear_sessions`);
* `app/backend/requirements.txt`: `pypdf`;
* `app/frontend/src/pages/RecipeViewer.jsx`: imports, the Guided tab and one branch;
* `app/frontend/src/pages/SettingsPage.jsx`: imports, one menu entry and one line; the update notes go through
  `fork/releases/releaseText.js` (import and one line);
* `app/frontend/src/components/AnnouncementModal.jsx`: import and two lines, release notes without raw HTML (GitHub's
  `<img>` tags showed as code);
* `app/frontend/src/components/YarnUploadModal.jsx`: imports, the stash hook, two calls in Save, the shop picture
  fetched through `/api/stash/image`, the ball band and Ball details blocks, and "Please check" on five boxes;
* `app/frontend/src/pages/InventoryPage.jsx`: import, one prop, one callback, the stash line on each yarn card;
* `app/frontend/src/pages/YarnViewer.jsx`: import and the Ball details section.

Guides are built, and ball bands read, with the AI address and key from the app's own Settings, AI page, and the
model chosen under Settings, Knitting upgrades (default Claude Haiku 5.5 through OpenRouter).

### Guided tab and upstream's view tabs

Since 1.0.0 upstream shows the view tabs only when AI is on or a text version exists
(`recipeViewAvailability` in `utils/viewerResume.mjs`). It also moves any view it does not know back to
Original, both on resume and in an effect. Four `fork` lines in `RecipeViewer.jsx` keep Guided working:
the tab bar also shows when Guided is on, the Text tab is then hidden unless a text version is available,
and `'guided'` is left alone on resume and by the effect while Guided is switched on.

### Upstream bug fixed in the fork

`utils/api.js` `addYarnColour` sent a form to an endpoint that only takes JSON, so "Add colour" on a yarn's page
failed with 422 (live included). It now sends the name and price as JSON and uploads the picture to the colour's own
picture endpoint. Marked `fork`. Worth reporting upstream with the other fixes.

Import wizard drafts that were uploaded but not yet saved (or were left with "Stop for now") showed in the library
as ordinary patterns, under their folder name. `list_recipes` now leaves out recipes whose `import_queue` row is
`staged`; the wizard still finds them. One line marked `fork` calling `fork_hooks.HIDE_STAGED_IMPORTS_SQL`.
Tests: `tests/test_fork_upstream_fixes.py`.

Deleting a project session, "clear all session history" and deleting a pattern failed with 500 once a session had
taken balls from the inventory, because `inventory_log` has foreign keys to the session and the recipe. Clearing
the history or deleting the pattern also left the database locked, so every page failed until a restart. Before
upstream deletes, `fork_hooks.before_sessions_delete` / `before_recipe_delete` clear those links in the same
transaction. The stock history rows stay (the balls were used and the count still shows it; the note names the
pattern). Deleting a pattern also removes the fork's guide for it, which would otherwise show on a new pattern with
the same title. Three lines marked `fork`. Tests: `tests/test_fork_upstream_fixes.py`.

Deleting a yarn or a colour that is in the stash or was used in a project failed in the same way (foreign key,
no try/finally, database locked). `app/yarns/service.py` `delete_yarn` and `delete_yarn_colour` now call
`fork_hooks.refuse_yarn_delete_if_used` first (one marked line each), which refuses with a plain message: "This yarn
can't be deleted because it is in your stash or was used in a project."

## Package updates

The library uses **upstream's package versions**: `requirements.txt` plus `requirements.lock`, `package.json`
plus `package-lock.json`, and upstream's digest-pinned base images (Python 3.12, Node 24). The only addition is
`pypdf` in `requirements.txt`, for the guide builder. Between 14 October and the 1.0.1 sync the fork ran its
own newer versions (Python 3.14, React 19, Vite 8). Those commits were dropped on 15 November 2026, because
upstream had pinned and security-patched its own versions and every bump conflicted with them. Nothing in
the fork needs the newer versions; the frontend builds and every test passes on upstream's.

If a sync conflicts in `requirements.txt`, take upstream's file and add `pypdf` back at the end.

**bcrypt stays on 4.x** (upstream pins 4.2.1). bcrypt 5 raises an error for passwords longer than 72 bytes, in
`checkpw` as well as `hashpw` (tested). Knitting Library treats the error as a wrong password, so anyone with a
longer password, possibly the `importer` account, could no longer sign in. If upstream ever moves to 5, check
that `_hash_password` and `_verify_password` cut the password to 72 bytes first.

The importer's packages are ours alone (Python 3.14) and never conflict.

**Checks before anything is published.** Both image workflows build the image, test it, and only then push:
the library image runs `.github/scripts/kl-smoke.py` (sign-in, PDF upload, page pictures), the importer image
runs `python -m app.selfcheck` (Chromium prints a PDF, poppler reads it).

**Monthly updates.** `.github/dependabot.yml` asks for update pull requests against `dev` for the importer's
packages and base image and for workflow actions, once a month. The library's own packages are left to
upstream. Each pull request runs the same tests and image checks as a push,
without publishing anything, so the result shows on the pull request. Merge the green ones into `dev`, try the
dev stack, then promote. Dependabot alerts (emails about known vulnerabilities) are on. Dependabot security
updates are off on purpose: they open pull requests against the default branch, `jeff`, which would skip `dev`.

## Tell upstream

Upstream fixed the tag bug in 1.0.1 (150862d, issue #21) with the same line as ours, so that patch was dropped.

Still worth reporting, all present in upstream 1.0.1 (see "Upstream bug fixed in the fork" for the details and
our fixes): "Add colour" fails with 422; deleting a pattern, a project session or the session history fails and
locks the database once a session has taken balls from inventory; deleting a used yarn or colour fails the same
way; unsaved import drafts show in the library. If upstream fixes one, remove our marked line on the next sync.

## Later: signing in with Keycloak

Knitting Library has its own login behind Pangolin, so Mary signs in twice. Adding OIDC touches authentication and the login screen. It is a bigger patch and the first one likely to collide with upstream. Decide on it separately.

## Status

15 November 2026: rebased onto upstream 1.0.1. The tag fix and the four package-update commits were
dropped, and the Guided tab was fitted to upstream's new view tabs. Backend tests: 256 passed. The one
failure, `test_chatgpt_integration`, fails the same way on plain upstream 1.0.1 under Python 3.14, so it is
not from the fork. The frontend builds, and its unit tests and locale check pass.


`sync-upstream.sh` was tested in three cases against local copies: no change, clean rebase, conflict. Both image builds have run on `jeff`.

`jeff` has been the default branch since 14 October 2026, so the weekly upstream check runs. It was run by
hand that day and passed.
