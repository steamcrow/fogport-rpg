# Adding a new entry — read this first

This page is written for an AI assistant (ChatGPT, Claude, or similar)
working in this repository. If you are about to write a new Python script
to publish something to Kanka, **stop** — you almost certainly don't need
to. Read this page instead.

## The one rule

**Publishing a new character, creature, location, item, or organization
never requires new code.** It only requires:

1. A new JSON file in the right `kanka_librarian/approved_*/` folder.
2. Running `python scripts/refresh_publish_menu.py`.
3. Telling Daniel the exact dropdown label to pick in
   `publish-approved.yml` under GitHub Actions.

If you find yourself about to create a new file under `scripts/` or a new
file under `.github/workflows/`, stop and re-read this page — you have
almost certainly missed the folder this entry belongs in.

## Which folder does my entry go in?

| Entry is a...   | Put the JSON file here                     |
|------------------|--------------------------------------------|
| Character        | `kanka_librarian/approved_characters/`      |
| Creature or people | `kanka_librarian/approved_creatures/`     |
| Location          | `kanka_librarian/approved/`                 |
| Item              | `kanka_librarian/approved_items/`           |
| Organization      | `kanka_librarian/approved_organizations/`   |
| Compiled episode or note | `kanka_librarian/approved_episodes/` or `approved_notes/` |

The file name (minus `.json`) becomes the dropdown label, e.g.
`approved_items/rusty-key.json` becomes `item: rusty-key`.

## The JSON shape to use

Every entry type above uses the same envelope. Only `section` and the
fields inside the one object in `proposals` change.

```json
{
  "schema_version": 1,
  "mode": "proposal-only",
  "campaign_id": 410879,
  "campaign_name": "Fogport",
  "create_order": ["my-new-thing"],
  "approval_questions": [],
  "proposals": [
    {
      "temp_id": "my-new-thing",
      "action": "create",
      "section": "items",
      "name": "The exact display name",
      "type": "A short type/category label",
      "is_private": false,
      "entry": "<p>The full description, as HTML.</p>",
      "fields": {},
      "resolved_references": [],
      "posts": [],
      "attributes": [],
      "relationships": [],
      "publication": {}
    }
  ],
  "approval": {
    "status": "approved",
    "approved_by": "Daniel Davis",
    "approved_at": "2026-08-14T00:00:00-07:00",
    "proposal_sha256": "REPLACE_ME"
  }
}
```

`section` must be one of: `characters`, `creatures`, `locations`,
`items`, `organizations`.

**Do not hand-write `proposal_sha256`.** It is a checksum of everything
above the `approval` block, and it must match exactly or publishing will
be refused (this is intentional — it proves the content wasn't edited
after Daniel approved it). Compute it with:

```bash
python3 -c "
import json
from kanka_librarian.publisher import approve_proposal
doc = json.load(open('kanka_librarian/approved_items/my-new-thing.json'))
doc.pop('approval', None)
approved = approve_proposal(doc, approved_by='Daniel Davis')
json.dump(approved, open('kanka_librarian/approved_items/my-new-thing.json', 'w'), indent=2)
"
```

That script reads the file, stamps a correct approval block (including
the checksum) onto it, and writes it back. Only run it after Daniel has
actually approved the content — the approval block is supposed to mean
something.

## Optional extras

- **A location has a required parent.** Add this to `publication`:
  `"publication": {"parent_name": "Fogport", "parent_link_phrase": "Fogport"}`
- **An item can optionally belong to a location.** Add this to
  `publication`: `"publication": {"location_name": "The Wayward Pint"}`
- **A GM-only (hidden) post.** Add to `posts`:
  `{"name": "GAMEMASTER SECRETS", "entry": "<p>...</p>", "visibility_id": 3}`
  Visibility 3 is required for every GM post; nothing else is accepted.
- **A main image.** Put the image file under `assets/<kind>/`, then add:
  `"artwork": {"main_image_path": "assets/items/rusty-key.png", "sha256": "..."}`
  Get the sha256 with `sha256sum assets/items/rusty-key.png`.

## Adding an era to an existing timeline

Eras aren't Kanka entities (no name/type/entry like the table above), so
they use their own simpler shape. Put a file in
`kanka_librarian/approved_eras/`:

```json
{
  "schema_version": 1,
  "mode": "proposal-only",
  "campaign_id": 410879,
  "campaign_name": "Fogport",
  "timeline_name": "Fogport History",
  "era": {
    "name": "The Drowned Years",
    "abbreviation": "DY",
    "start_year": -40,
    "end_year": 0,
    "visibility": "all"
  }
}
```

Stamp its approval block with:

```bash
python3 -c "
import json
from datetime import datetime, timezone
from kanka_librarian.era_publish import approve_era_document
doc = json.load(open('kanka_librarian/approved_eras/the-drowned-years.json'))
doc.pop('approval', None)
approved = approve_era_document(doc, approved_by='Daniel Davis', approved_at=datetime.now(timezone.utc).isoformat())
json.dump(approved, open('kanka_librarian/approved_eras/the-drowned-years.json', 'w'), indent=2)
"
```

This only adds an era to a timeline that **already exists**
(`timeline_name` must match one exactly). Creating a brand-new timeline
is rarer and still needs a dedicated script — ask Daniel before building
one.

## After the file is ready

```bash
python scripts/refresh_publish_menu.py
python -m unittest discover -s tests
```

Both must succeed before telling Daniel the entry is ready to publish. If
`refresh_publish_menu.py` doesn't show your new subject, re-check the
folder and the `section` field — those are the two things that route it.

## When you genuinely need new code

A handful of entry types (portraits, world map markers, galleries,
ability blocks, main images for existing entries) are not yet folded into
the generic system and do still have their own scripts and workflows.
If you believe you're in one of those cases, check
`scripts/publish_menu.py` (the `OVERRIDES` and `FOLDER_ROUTES` tables) and
`.github/workflows/` first to confirm no existing script already does
what you need, before writing anything new.
