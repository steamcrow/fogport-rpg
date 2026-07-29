# Retired Kanka publishers — 2026-07-28

These files are historical records only. They are intentionally outside active
GitHub Actions and the runnable `scripts/` directory, and use the `.disabled`
suffix so they cannot be selected as a publisher by mistake.

## Why retired

The Saint Orra and Lastlight repair publishers mixed core publication with
hierarchy rewrites, image uploads, map pins, posts, and HTML-sensitive
cross-links. A failure in any optional step could stop or misreport the core
entry. They also ran automatically on a code push.

The active rule for Fogport is:

1. Manual workflow dispatch only.
2. One purpose per workflow.
3. Core entry receipt first.
4. Optional image, links, map pins, and hierarchy repairs are independent.
5. A Kanka receipt—not a merge or a green-looking run—is the only proof of
   publication.

Do not restore or run these files. Rebuild any needed operation using the
current shared publisher and the rules above.
