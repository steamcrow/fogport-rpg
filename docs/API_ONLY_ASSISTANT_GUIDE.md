# Using this repo through the GitHub API only (no shell access)

This page is for an AI assistant that has a GitHub token for this repo
(`steamcrow/fogport-rpg`) but does **not** have a shell where it can clone
the repo and run Python — for example, ChatGPT calling GitHub's REST API
directly through a configured Action.

If you *can* run `git clone` and `python` against this repo, you don't
need this page — use [`ADDING_A_NEW_ENTRY.md`](ADDING_A_NEW_ENTRY.md)
instead, which assumes that.

## What your token can and can't do

With **Contents: Read and write** and **Actions: Read and write** on this
one repo, you can:

- Read any file in the repo.
- Create or update files (e.g. a new `approved_*/` manifest).
- Trigger (`workflow_dispatch`) any existing workflow.
- Check a workflow run's status and read its logs.
- Download workflow run artifacts.

You **cannot**:

- Run `scripts/refresh_publish_menu.py` or the test suite — those need a
  real shell. Skip them; see "Publishing it" below for the workaround.
- Edit files under `.github/workflows/` — your token doesn't have
  Workflow permission, on purpose. If you think a workflow file itself
  needs to change, stop and tell Daniel rather than trying anyway.
- Read the actual Kanka API token. It's a GitHub Actions secret; nothing
  outside a running workflow can ever read it back out, including you.

## Step 1 — See what already exists

Trigger the read-only snapshot, then read its output:

```
POST /repos/steamcrow/fogport-rpg/actions/workflows/export-campaign-snapshot.yml/dispatches
Body: {"ref": "main"}
```

Poll `GET /repos/steamcrow/fogport-rpg/actions/runs?branch=main&per_page=1`
until `status` is `completed`. Then:

```
GET /repos/steamcrow/fogport-rpg/actions/runs/{run_id}/artifacts
```

Download the `FOGPORT-CAMPAIGN-SNAPSHOT` artifact (a zip containing
`campaign_snapshot.json`) via the `archive_download_url` it returns. That
file lists every character/creature/location/organization/item/etc. by
name, type, and Kanka id — use it to avoid proposing a duplicate and to
get the right `entity_id` for cross-references.

This snapshot can be a few minutes stale. That's fine — it's not the
safety-critical path. The actual publish step (Step 3) always re-checks
Kanka live before writing anything, regardless of what the snapshot says.

## Step 2 — Write the approved manifest

Follow [`ADDING_A_NEW_ENTRY.md`](ADDING_A_NEW_ENTRY.md) for the folder
and JSON shape. The one thing that page assumes you can't do here is
compute the approval checksum with the repo's own code — do it yourself
instead, with this same algorithm:

```python
import hashlib, json

def digest(document_without_approval: dict) -> str:
    canonical = json.dumps(
        document_without_approval,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
```

Run this yourself (your own code tool, not the repo) on your document
**with the `approval` key removed**, then attach:

```json
"approval": {
  "status": "approved",
  "approved_by": "Daniel Davis",
  "approved_at": "<ISO 8601 timestamp>",
  "proposal_sha256": "<the digest you just computed>"
}
```

**One field-name trap:** entities (characters/creatures/locations/items/
organizations) use `"proposal_sha256"`. Eras use `"document_sha256"`
instead — same algorithm, different key name. Get this wrong and
publishing fails safely with a clear "approval is invalid" message, but
it's an easy thing to trip on, so double-check which shape you're using.

`approved_by` should always be `"Daniel Davis"` — not your own name, not
"ChatGPT." Eras enforce this exactly (anything else is rejected); the
entity path is technically more lenient (any non-empty string passes),
but use `"Daniel Davis"` everywhere regardless, for a consistent approval
trail. Daniel is the one approving; you're the one typing it in on his
behalf, the same as this page assumes he's reviewed what you drafted
before you write the file.

Write the file with:

```
PUT /repos/steamcrow/fogport-rpg/contents/kanka_librarian/approved_items/rusty-key.json
Body: {
  "message": "Add approved item: rusty-key",
  "content": "<base64-encoded JSON>",
  "branch": "main"
}
```

(Add `"sha": "<existing file's sha>"` only if you're overwriting a file
that already exists — GitHub requires it for updates, rejects it for new
files.)

## Step 3 — Publish it

**Skip `refresh_publish_menu.py` entirely.** The dropdown menu is a
convenience for humans browsing recent subjects — it is not required for
publishing. Use the `older_subject` free-text field instead, which takes
an exact label and works whether or not it's in the dropdown:

```
POST /repos/steamcrow/fogport-rpg/actions/workflows/publish-approved.yml/dispatches
Body: {
  "ref": "main",
  "inputs": {
    "subject": "-- choose a subject --",
    "older_subject": "item: rusty-key"
  }
}
```

The label format is always `"<kind>: <filename-without-.json>"` — e.g.
your file `approved_items/rusty-key.json` becomes `"item: rusty-key"`.

## Step 4 — Confirm it actually worked

Poll the run the same way as Step 1. **A green run is not proof by
itself** — that's a rule this whole repo follows, not just you. Check the
run's logs (`GET /repos/steamcrow/fogport-rpg/actions/runs/{run_id}/jobs`,
then the job's log URL) for the printed receipt, which includes the
Kanka entity id and a direct `overview_url`. Report that URL back to
Daniel, not just "it succeeded."

If the run failed, read the failure message from the logs and report it
plainly — do not retry with guessed changes, and do not edit the
manifest to "make the error go away" without understanding what it
actually means. A rejected approval, a duplicate-name refusal, or a
campaign-lock failure are all the safety system doing its job correctly.

## If something doesn't fit this page

If a task needs editing a workflow file, deleting something, or anything
else outside "add one new manifest, publish it, read the result" — stop
and ask Daniel rather than working around your token's limits. The
limits are deliberate.
