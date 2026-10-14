# Share from Safari (iPhone and iPad)

**Prototype. Not yet tried on a real iPhone.** The server side is tested. The Shortcut steps below are written
from how Shortcuts works, not from a run on Mary's phone. Expect small differences in the wording of actions
between iOS versions.

## What it does

Mary opens a DROPS pattern in Safari, taps Share, and picks "Add to Knitting Library". A Shortcut:

1. copies the page she is looking at (the page itself, as Safari has it),
2. makes a PDF of it on the phone,
3. sends both to the importer, and
4. opens the importer in Safari at the "Check details" step.

She checks the details and adds the pattern as usual. Nothing goes into the library until she does.

### Why this gets past the "human check"

It does not get past it. Safari has already passed DROPS's check when Mary opened the page. The Shortcut
reads the page Safari already has. The importer does not fetch anything from DROPS on this route.

## Limits for now

* **DROPS pattern pages only.** Other sites get a "DROPS only, for now" message. Other pattern sites and yarn
  shop pages are the next step.
* **Untested on a phone:**
  * Whether "Make PDF" prints the page Safari already has, or loads the address again. If it loads it again,
    DROPS may answer with a human check, the PDF is refused, and the importer opens at "Add the PDF". Mary can
    then add a PDF by hand.
  * Whether a PDF made by "Make PDF" reads as well as one printed from a computer. It uses the screen layout,
    not DROPS's print layout.

## 1. Server (Jeff)

Try this on the dev stack first.

1. Make a key. On any Linux machine:

   ```
   openssl rand -hex 32
   ```

2. Add it to the dev stack's `.env` in Arcane, and redeploy:

   ```
   SHARE_TOKEN=the-64-characters-from-step-1
   ```

3. **Pangolin rule.** The Shortcut cannot sign in to Keycloak, so one path must skip SSO. On the dev
   resource, add a rule:

   | Action | Match | Value |
   | --- | --- | --- |
   | Bypass Auth | Path | `/import/api/share` |

   Use exactly that path, with no `*`. Pangolin's docs say a pattern without a wildcard matches only that path.
   Everything else on the resource stays behind SSO. Source: https://docs.pangolin.net/manage/access-control/rules.md

4. **Check the rule did only that.** In a private browser window:
   * `https://knit-dev.wighttrash.uk/import/` should send you to the Keycloak sign-in page.
   * `https://knit-dev.wighttrash.uk/import/api/share` should **not** show Keycloak. It shows a small error,
     because that address only accepts uploads.

   If the first one loads the importer without signing in, remove the rule and stop.

### What the open path can do

Anyone on the internet can reach `/import/api/share`. Without the key it refuses everything. With the key it
can only make a draft: it cannot add to the library, read the library, or see other drafts. Drafts expire after
`DRAFT_TTL_HOURS` (24). Uploads are capped at `MAX_UPLOAD_MB` (50).

The key lives in the Shortcut on Mary's phone, and in iCloud if her Shortcuts sync. To revoke it, change
`SHARE_TOKEN` and redeploy. The old Shortcut then gets "The Shortcut's key does not match".

## 2. iPhone settings (once)

Settings, Apps, Shortcuts, Advanced: switch on **Allow Running Scripts**. Without it the Shortcut cannot read
the page.

## 3. Build the Shortcut

In the Shortcuts app, tap **+**. Name it **Add to Knitting Library**.

Open the Shortcut's details (the **i** button, or the name at the top, depending on iOS version):
switch on **Show in Share Sheet**. Set what it receives to **Safari web pages** only.

Add these actions in order. Words in **bold** are action names to search for.

1. **Run JavaScript on Web Page**. Input: *Shortcut Input*. Replace the sample script with:

   ```
   completion({ url: location.href, html: document.documentElement.outerHTML });
   ```

2. **Make PDF**. Input: *Shortcut Input*.

3. **Get Dictionary Value**. Get *Value* for key `url` in *JavaScript Result*.
   Long-press the result and rename the variable to `Page URL`. (Renaming is optional but makes step 5 clearer.)

4. **Get Dictionary Value**. Get *Value* for key `html` in *JavaScript Result*. Rename to `Page HTML`.

5. **Get Contents of URL**.
   * URL: `https://knit-dev.wighttrash.uk/import/api/share`
   * Tap **Show More**. Method: **POST**.
   * Headers: add one. Key `Authorization`, value `Bearer ` followed by the key from step 1 of the server
     set-up. There is one space after `Bearer`.
   * Request Body: **Form**. Add three fields:

     | Key | Type | Value |
     | --- | --- | --- |
     | `url` | Text | `Page URL` |
     | `html` | Text | `Page HTML` |
     | `pdf` | File | *PDF* (from step 2) |

6. **Get Dictionary Value**. Get *Value* for key `open` in *Contents of URL*.

7. **If**. Input: *Dictionary Value* (from step 6), condition **has any value**.
   * Inside the If: **Open URLs**, with *Dictionary Value* from step 6.
   * Under **Otherwise**: **Get Dictionary Value** for key `message` in *Contents of URL*, then
     **Show Alert** (or **Show Result**) with that value.

The first time it runs, iOS asks to allow the Shortcut to run a script on garnstudio.com and to connect to
`knit-dev.wighttrash.uk`. Tap **Allow**.

## 4. Try it

1. In Safari, open a DROPS pattern page.
2. Tap Share, then **Add to Knitting Library**.
3. Safari should open the importer at "Check details". If you have not signed in to the library on that phone
   recently, Keycloak asks first, then you land on the same page.

Things to note for the next session, whatever happens:

* Did it reach "Check details", or stop at "Add the PDF"? If the latter, what did the PDF check say?
* What did the alert say, if one appeared?
* iOS version, and iPhone or iPad.

## For the live stack later

Once it works on dev: `SHARE_TOKEN` in the live `.env`, the same Pangolin rule on the live resource, and the
Shortcut's URL changed to `https://knit.wighttrash.uk/import/api/share`. Use a different key for live.

## The API, for reference

`POST /api/share` (also `/import/api/share`)

* Header: `Authorization: Bearer <SHARE_TOKEN>`. The usual `X-Requested-With` header is not needed here.
* Form fields: `url` (text, required), `html` (text or file), `pdf` (file, optional). At least one of `html` and
  `pdf`.
* Reply, always JSON: `{"ok": true|false, "open": "<address to open, or empty>", "message": "<plain English>"}`.
* Status codes: 200 draft made, 401 wrong key, 404 sharing off, 413 too big, 422 not a usable DROPS page.
