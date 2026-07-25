# Approval and publish contract

The Librarian turns reviewed findings into a `proposal-only` JSON document. Publishing is a
separate operation and is disabled unless all of these conditions are true:

1. The campaign is MAELSTROS (`29474`). Fogport (`410879`) remains protected.
2. Every ambiguity and unresolved reference has been cleared.
3. Daniel explicitly approves the complete batch.
4. The approval envelope contains a SHA-256 digest of that exact batch.
5. The publisher is invoked with its explicit execute switch.

Any edit after approval changes the digest and invalidates the approval. Delete actions are not
implemented.

## Two-pass publishing

The publisher creates new entities in dependency order as minimal shells. It captures both the
Kanka resource ID and global entity ID from every response. Only after all new IDs exist does it
write descriptions and updates, replacing forward references with durable Kanka mentions such as
`[entity:12345|Nine Spoons]`.

This is what allows a new Byl entry and a new Nine Spoons entry to be approved in the same batch
without guessing an ID or leaving a broken link.

## Current boundary

This milestone publishes core entity records and inline-linked descriptions. GM/private posts,
attributes, relationships, tags that do not already have IDs, and images remain proposal data until
their own write adapters and tests are added.
