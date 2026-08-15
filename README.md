# Kanka Librarian

A safe, approval-first bridge between AI-driven RPG sessions and Kanka.

Fogport is the first production campaign. The Librarian can publish verified
characters, creatures, and nested locations, attach administrator-only
Gamemaster posts, and process a whole approved episode as one batch.

**If you are an AI assistant about to add a new entry, read
[`docs/ADDING_A_NEW_ENTRY.md`](docs/ADDING_A_NEW_ENTRY.md) first.** It is
short, and it will stop you from writing code you don't need to write.

## Normal Fogport workflow

1. Play an episode or approve an individual entry.
2. Review one compact public-canon change set.
3. Say **Publish** once.
4. The Librarian (or an AI assistant following
   [`docs/ADDING_A_NEW_ENTRY.md`](docs/ADDING_A_NEW_ENTRY.md)) writes one
   approved JSON file into the matching `kanka_librarian/approved_*/`
   folder — **no new script and no new workflow file are ever needed for a
   character, creature, location, item, or organization.**
5. Daniel opens `publish-approved.yml` under GitHub Actions, picks the
   subject from the dropdown (or types its exact label into
   "older_subject" if it isn't in the recent list), and presses **Run
   workflow** once. There is no filename to edit and no code to enter.
   For annual observances, that single run publishes the event records
   and then attaches and verifies their calendar reminders in sequence.
6. Treat the run as successful only when the Kanka exact-read-back receipts
   confirm every requested phase. A green GitHub check alone is not proof.

The GitHub repository is plumbing, not the approval interface. Daniel's
approval in the Fogport conversation is the content approval. The manual
workflow button exists only because commits made by the GitHub integration do
not trigger another Actions workflow.

## Production workflow

**`publish-approved.yml` is the normal publishing interface.** It shows a
dropdown of recently-approved subjects; picking one and pressing **Run
workflow** publishes it and verifies the result. Behind the scenes it
routes each subject to the right publisher script — see
`scripts/publish_menu.py` for the exact routing table, and
`docs/ADDING_A_NEW_ENTRY.md` for how to add a new subject.

A small number of subjects (portraits, map markers, galleries, ability
blocks, and a few other one-off pieces) aren't yet folded into the
dropdown and still have their own dedicated workflow file in
`.github/workflows/`. Those are legitimate exceptions, not leftovers.

Historical single-subject workflows that the dropdown has fully replaced
have been retired to
`archive/retired-single-subject-workflows-2026-08-14/` — see that
folder's README if you're wondering where an old workflow went.

The following generic workflows are advanced maintenance fallbacks. They have
no default filename, are labeled **Advanced** in GitHub Actions, and require an
operator to deliberately enter an exact approved filename:

- `publish-approved-batch.yml`
- `publish-approved-character.yml`
- `publish-approved-creature.yml`
- `publish-approved-location.yml`
- `crosslink-fogport.yml`

`ci.yml` runs the safety tests on supported Python versions.

Batch runs are sequential and safe to rerun. Each item uses exact-name
duplicate detection, updates an existing matching record in place, verifies
the public entity through Kanka, verifies every GM post as administrator-only,
and emits both an individual and combined receipt.

Every publisher rebuilds a campaign-wide registry from Kanka before rendering
new text. The registry records both the resource ID used for updates and the
global entity ID used in `[entity:ID|text]` links. Canonical names are
automatic; human-approved aliases live in
`kanka_librarian/crosslink_aliases.json`.

The cross-linker changes only unlinked text. It protects HTML tags and existing
Kanka links, links only the first useful occurrence of each target, rejects
ambiguous aliases, avoids self-links, and never links a private target from
public text. The rebuilt registry and exact read-back receipt are retained as
workflow artifacts rather than becoming a hand-maintained ID database.

## Lessons from the Vauntin publication

- Never prefill a generic publisher with an unrelated entity. A green run can
  faithfully republish the default while leaving the intended entity untouched.
- Prefer a dedicated one-button workflow whenever Daniel is asked to publish.
  The subject and manifest must be visible in the workflow and job names.
- Never replace approved artwork in place without updating and reapproving its
  checksum-locked manifest. A checksum mismatch is a correct stop, not an error
  to bypass.
- A workflow completing is not publication proof. The receipt must confirm the
  intended name, campaign, entity ID, image read-back, private posts, and direct
  Kanka Overview URL.
- Run the Librarian safety tests immediately before every production write.
- Preserve the concurrency lock so two Fogport writes cannot overlap.

## Safety rules

- Never commit a Kanka API token.
- Lock every production write to Fogport campaign `410879` and verify the
  campaign name before writing.
- Require an approval digest; reject any proposal or batch edited afterward.
- Require content-locked artwork checksums and stop if the bytes changed.
- Never expose delete operations through the publishing workflows.
- Refuse ambiguous duplicate names instead of guessing.
- Preserve nested locations and Kanka entity links.
- Treat cross-link cleanup as idempotent: a safe rerun adds no duplicate or
  nested links.
- Store hidden material in separately labeled `GAMEMASTER SECRETS` posts with
  administrator-only visibility.
- A workflow trigger, queue entry, API write, or green check is not success.
  Only exact Kanka read-back plus the correct receipt is success.

## Episode batch format

Approved batches live in `kanka_librarian/approved_batches/`. Each batch lists
already approved proposal files in dependency order:

```json
{
  "schema_version": 1,
  "mode": "approved-batch",
  "campaign_id": 410879,
  "campaign_name": "Fogport",
  "items": [
    {
      "kind": "location",
      "proposal": "kanka_librarian/approved/example-room.json"
    },
    {
      "kind": "character",
      "proposal": "kanka_librarian/approved_characters/example-person.json"
    },
    {
      "kind": "creature",
      "proposal": "kanka_librarian/approved_creatures/example-creature.json"
    }
  ],
  "approval": {
    "status": "approved",
    "approved_by": "Daniel Davis",
    "batch_sha256": "sha256-of-the-document-without-the-approval-object"
  }
}
```

The batch publisher rejects path traversal, unsupported entity kinds,
duplicates, missing proposals, campaign mismatches, and edits made after
approval. If an item fails, the batch stops. Previously verified items are safe
to process again on the next run.

## Development

Python 3.11 or newer is supported.

```bash
pip install -r requirements.txt
python -m unittest discover -s tests
```

The Librarian intentionally keeps its small Kanka adapter for now. Reliability
patterns from `python-kanka` and `mcp-kanka` are being adopted incrementally
without making the working Fogport publisher depend on either package.
