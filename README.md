# Kanka Librarian

A safe, approval-first bridge between AI-driven RPG sessions and Kanka.

Fogport is the first production campaign. The Librarian can publish verified
characters and nested locations, attach administrator-only Gamemaster posts,
and process a whole approved episode as one batch.

## Normal Fogport workflow

1. Play an episode.
2. Review one compact public-canon change set.
3. Say **Publish** once.
4. Run the prepared episode workflow once.
5. Treat the run as successful only when every item has an exact Kanka
   read-back receipt and direct Overview URL.

The GitHub repository is plumbing, not the approval interface. Daniel's
approval in the Fogport conversation is the content approval. The manual
workflow button exists only because commits made by the GitHub integration do
not trigger another Actions workflow.

## Production workflows

- `publish-approved-batch.yml`: preferred episode workflow; publishes an
  ordered mixture of approved characters and locations.
- `publish-approved-character.yml`: single-character fallback.
- `publish-approved-location.yml`: single-location fallback.
- `ci.yml`: runs the safety tests on supported Python versions.

Batch runs are sequential and safe to rerun. Each item uses exact-name
duplicate detection, updates an existing matching record in place, verifies
the public entity through Kanka, verifies every GM post as administrator-only,
and emits both an individual and combined receipt.

## Safety rules

- Never commit a Kanka API token.
- Lock every production write to Fogport campaign `410879` and verify the
  campaign name before writing.
- Require an approval digest; reject any proposal or batch edited afterward.
- Never expose delete operations through the publishing workflows.
- Refuse ambiguous duplicate names instead of guessing.
- Preserve nested locations and Kanka entity links.
- Store hidden material in separately labeled `GAMEMASTER SECRETS` posts with
  administrator-only visibility.
- A workflow trigger, queue entry, or API write is not success. Only exact
  Kanka read-back plus a receipt is success.

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

The Librarian intentionally keeps its small Kanka adapter for now. The useful
reliability patterns from `python-kanka` and `mcp-kanka` are being adopted
incrementally, but their current packages pin Python to a runtime newer than
the established Fogport workflow.
