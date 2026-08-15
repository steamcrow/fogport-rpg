# Retired single-subject publish workflows — 2026-08-14

These 31 workflow files are historical records only. They use the
`.disabled` suffix so GitHub Actions cannot run them and no one can select
them by mistake.

## Why retired

Each of these was a dedicated "press this one button to publish this one
subject" workflow, from before the single dropdown menu
(`publish-approved.yml`) existed. Every subject they published is now
published exactly the same way — same manifest, same publisher script,
same safety checks — through the one dropdown menu instead:

1. Open `publish-approved.yml` under GitHub Actions.
2. Choose the subject from the dropdown (or type its exact label into
   "older_subject" if it has scrolled out of the recent list).
3. Press **Run workflow**.

Having two working paths to publish the same thing was confusing —
especially for an AI assistant reading the repository, which had no way
to know the dedicated button was the old path and the dropdown was the
current one. Keeping only the dropdown removes that ambiguity.

## What was NOT retired

Workflows that do something the dropdown menu cannot yet do on its own —
portraits, world map markers, image-only galleries, ability blocks, and a
few subjects with genuinely bespoke publish steps — were left in place in
`.github/workflows/`. Folding those into the generic menu is future work,
not part of this cleanup.

## Do not restore or run these files

If one of these subjects ever needs to be republished, use the dropdown
menu in `publish-approved.yml`. The underlying publisher scripts these
workflows used to call directly are still active and still used by the
menu — only the dedicated one-button workflow wrapper was retired.
