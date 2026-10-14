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

Only the three patch commits touch upstream files. Everything else is new files, so it cannot conflict with upstream.

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
