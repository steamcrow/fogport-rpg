# Note-to-proposal contract

The Librarian's first transformation stage accepts normalized findings from campaign notes and compares them with a full Kanka snapshot. It produces a review file only. It never writes to Kanka.

Each finding identifies an action, entity section, name, proposed entry, and explicit entity references. New records use temporary IDs. Nested creates point to a parent temporary ID.

The proposal builder:

- matches names exactly after Unicode, case, and whitespace normalization;
- retains collisions instead of guessing;
- distinguishes existing entities, approved pending creates, ambiguous matches, and unresolved references;
- orders new nested entities parent-first;
- inserts inline mentions only when a real Kanka entity ID already exists;
- leaves forward references unrendered until the approved create pass returns real IDs;
- blocks dependent updates when a reference is ambiguous or unresolved;
- emits approval questions separately;
- performs no Kanka writes.

AI extraction from raw prose will feed this contract later. Keeping extraction separate from resolution makes the approval and link behavior deterministic and testable.
