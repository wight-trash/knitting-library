# This fork

This is `wight-trash/knitting-library`, a fork of [ZeetLex/knitting-library](https://github.com/ZeetLex/knitting-library).

The `jeff` branch is upstream `main` plus a few things on top.

| Where | What |
| --- | --- |
| First patch commit | Restores the `recipe_tags` insert in `_save_cats_tags`. Upstream creates tags but never links them to the recipe, so tags never show up. |
| Second patch commit | Makes `[label](https://...)` links clickable in the text version viewer. Needed for video, lesson and yarn links. |
| Third patch commit | Adds an "Import from DROPS" link to the sidebar and the Add menu. It goes to `/import/`, where the importer is served. Only `AppShell.jsx`, `AppShell.css` and `en.js` change. |
| `importer/` | The importer, a separate app that adds patterns from websites to Knitting Library. Own README. |
| `deploy/docker-compose.yml` | The live stack: both apps on one private network. |
| `deploy/docker-compose.dev.yml` | A test copy of the stack, built from `dev`. Runs beside the live one. |
| `.github/workflows/` | Image builds for both apps, and a weekly upstream check. |
| `sync-upstream.sh` | Keeps the `jeff` branch in step with upstream. |

The three patch commits above touch upstream files, and so do the package updates (see "Package updates"
below). Everything else is new files, so it cannot conflict with upstream.

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

* The tag fix sits in a function that has not changed since the backend refactor. `repository.py` changed in only three commits since July.
* The nav link patch adds an item to two menus in `AppShell.jsx`, a file upstream edits often. It is the most likely patch to need a hand fix.
* The link patch touches the last lines of `MarkdownView`, a small part of a very large file.
* Upstream is slowing down: about 77 commits in June, about 10 in September.
* Upstream only publishes `latest`, `beta` and `0.9.1` on Docker Hub, so a version tag cannot be relied on. The image built here is pinned to a commit.

Expect a few minutes a month. Most months nothing needs doing.

```
./sync-upstream.sh --check     # how far behind, and would the rebase be clean
./sync-upstream.sh             # rebase onto upstream main
git push --force-with-lease origin jeff
```

The weekly workflow runs the check and fails if the rebase would conflict. GitHub emails you about failed runs. The push builds new images. Then update the stack in Arcane.

If a rebase stops on a conflict, git names the file. Keep upstream's new code, put the patch's lines back, then `git add` and `git rebase --continue`.

## Package updates

The fork runs newer packages than upstream. These commits change upstream files, so they are the ones most
likely to conflict on a sync:

| What | Files | Notes |
| --- | --- | --- |
| Backend packages, Python 3.14, Node 24 | `app/backend/requirements.txt`, `Dockerfile` | bcrypt held at 4.3.0 (see below) |
| Unused frontend packages removed | `app/frontend/package.json`, `package-lock.json` | `ajv`, `react-pdf`, `react-dropzone` were never imported |
| Vite 8, React 19, lucide-react 0.577 | same | lucide-react 1.x dropped the GitHub icon the app uses |

The importer's packages are ours alone and never conflict.

**If a sync conflicts in `package-lock.json`,** do not merge it by hand. Take upstream's `package.json`, put our
version numbers back, then regenerate the lock file and continue:

```
cd app/frontend && npx npm@11 install --legacy-peer-deps && cd ../..
git add app/frontend/package.json app/frontend/package-lock.json && git rebase --continue
```

Once upstream reaches the same versions, our commits become empty and drop out of the rebase.

**bcrypt stays on 4.x.** bcrypt 5 raises an error for passwords longer than 72 bytes, in `checkpw` as well as
`hashpw` (tested). Knitting Library treats the error as a wrong password, so anyone with a longer password,
possibly the `importer` account, could no longer sign in. Moving to 5 needs `_hash_password` and
`_verify_password` to cut the password to 72 bytes first, as bcrypt 4 did silently. That belongs upstream.

**Checks before anything is published.** Both image workflows build the image, test it, and only then push:
the library image runs `.github/scripts/kl-smoke.py` (sign-in, PDF upload, page pictures), the importer image
runs `python -m app.selfcheck` (Chromium prints a PDF, poppler reads it).

**Weekly updates.** `.github/dependabot.yml` asks for update pull requests against `dev` for every package list,
base image and workflow action. Dependabot reads that file only from the default branch, so it is off while the
default branch is `main`.

## Tell upstream

The tag bug is worth reporting upstream. If upstream applies a fix, the first patch commit drops out by itself on the next rebase.

## Later: signing in with Keycloak

Knitting Library has its own login behind Pangolin, so Mary signs in twice. Adding OIDC touches authentication and the login screen. It is a bigger patch and the first one likely to collide with upstream. Decide on it separately.

## Status

`sync-upstream.sh` was tested in three cases against local copies: no change, clean rebase, conflict. Both image builds have run on `jeff`.
The `dev` image tags have not been built yet.

The weekly upstream check has never run. GitHub runs scheduled workflows only from the default branch,
and this fork's default branch is `main`, which does not have the workflow. Making `jeff` the default
branch would fix it.
