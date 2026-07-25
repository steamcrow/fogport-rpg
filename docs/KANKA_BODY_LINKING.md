# Kanka body-copy linking rules

Inline entity mentions in descriptions and entity posts are required Librarian output.

## Durable links

- Resolve names and known aliases against the campaign entity registry.
- Render recognized mentions with Kanka's ID-based entity syntax.
- Preserve existing valid entity mentions.
- Link the first useful occurrence by default instead of cluttering every repetition.
- Treat ambiguous names as approval questions; never guess an entity ID.
- Keep structured fields, such as a character's location, separate from inline links.

## Forward references

Approved batches must use two passes:

1. Create approved new entities in dependency order and capture their real Kanka IDs.
2. Render descriptions, GM/private posts, structured fields, and relationships from that completed ID registry.

If Byl Häsbaine's description mentions Nine Spoons and Nine Spoons does not exist, create Nine Spoons first. Only after Kanka returns its ID may the Librarian render Byl's inline link.

If an entity cannot be created or resolved, mark the mention unresolved in the proposal and stop the dependent update. Never emit a guessed ID, broken link, or duplicate entity.

Foundational location chains are parent-first. For Fogport > Nine Spoons > Twisted Eel, each approved parent must have a real ID before dependent body copy is rendered.
