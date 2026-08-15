"""Safety tests for the one-menu publish system."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import publish_menu  # noqa: E402


class MenuTests(unittest.TestCase):
    def test_every_entry_points_at_real_files(self) -> None:
        entries = publish_menu.build_menu()
        self.assertGreater(len(entries), 0)
        for entry in entries:
            manifest = REPOSITORY_ROOT / entry["manifest"]
            script = REPOSITORY_ROOT / entry["script"]
            self.assertTrue(manifest.is_file(), f"missing manifest: {entry}")
            self.assertTrue(script.is_file(), f"missing publisher: {entry}")

    def test_every_manifest_stays_inside_the_approved_folders(self) -> None:
        librarian = (REPOSITORY_ROOT / "kanka_librarian").resolve()
        for entry in publish_menu.build_menu():
            resolved = (REPOSITORY_ROOT / entry["manifest"]).resolve()
            self.assertTrue(
                resolved.is_relative_to(librarian),
                f"manifest escaped the approved folders: {entry}",
            )

    def test_multi_phase_calendar_subjects_are_excluded(self) -> None:
        labels = {entry["label"] for entry in publish_menu.build_menu()}
        for label in labels:
            self.assertNotIn("annual-observances", label)
            self.assertNotIn("fogport-calendar", label)

    def test_bespoke_manifests_route_to_their_dedicated_scripts(self) -> None:
        routes = {e["label"]: e["script"] for e in publish_menu.build_menu()}
        self.assertEqual(
            routes.get("character: inspector-adelaide-voss"),
            "scripts/publish_inspector_adelaide_voss.py",
        )
        self.assertEqual(
            routes.get("organization: daughters-last-bell"),
            "scripts/publish_daughters_last_bell.py",
        )

    def test_compiled_episodes_are_labeled_episodes_wherever_they_live(self) -> None:
        routes = {e["label"]: e["script"] for e in publish_menu.build_menu()}
        self.assertEqual(
            routes.get("episode: gutterkin"),
            "scripts/publish_compiled_episode.py",
        )

    def test_compiled_notes_are_labeled_notes(self) -> None:
        routes = {e["label"]: e["script"] for e in publish_menu.build_menu()}
        self.assertEqual(
            routes.get("note: fogport-cults"),
            "scripts/publish_compiled_episode.py",
        )
        self.assertNotIn("episode: fogport-cults", routes)

    def test_white_eye_secrets_are_one_compiled_canon_menu_subject(self) -> None:
        routes = {e["label"]: e["script"] for e in publish_menu.build_menu()}
        self.assertEqual(
            routes.get("canon: white-eye-society-secrets"),
            "scripts/publish_compiled_episode.py",
        )
        self.assertNotIn("image: white-eye-society-secrets", routes)

    def test_sentinel_and_unknown_labels_are_refused(self) -> None:
        with self.assertRaises(SystemExit):
            publish_menu.resolve(publish_menu.SENTINEL)
        with self.assertRaises(SystemExit):
            publish_menu.resolve("")
        with self.assertRaises(SystemExit):
            publish_menu.resolve("character: ../../etc/passwd")

    def test_workflow_menu_matches_the_generated_menu(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "publish-approved.yml"
        ).read_text()
        for entry in publish_menu.visible_menu():
            self.assertIn(
                f'- "{entry["label"]}"',
                workflow,
                f"menu is stale; run scripts/refresh_publish_menu.py "
                f"(missing {entry['label']!r})",
            )

    def test_workflow_shows_newest_subjects_and_intentional_pins(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "publish-approved.yml"
        ).read_text()
        visible = publish_menu.visible_menu()
        expected_labels = [entry["label"] for entry in visible]

        begin = "          # BEGIN AUTO-MENU (run scripts/refresh_publish_menu.py)\n"
        end = "          # END AUTO-MENU\n"
        self.assertIn(begin, workflow)
        self.assertIn(end, workflow)
        menu_text = workflow.split(begin, 1)[1].split(end, 1)[0]
        actual_labels = []
        for line in menu_text.splitlines():
            stripped = line.strip()
            if not stripped.startswith('- "') or not stripped.endswith('"'):
                continue
            label = stripped[3:-1]
            if label != publish_menu.SENTINEL:
                actual_labels.append(label)

        self.assertEqual(actual_labels, expected_labels)
        self.assertIn("older_subject:", workflow)

    def test_dropdown_choice_beats_optional_free_text(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "publish-approved.yml"
        ).read_text()
        expression = (
            "inputs.subject != '-- choose a subject --' "
            "&& inputs.subject || inputs.older_subject"
        )
        self.assertEqual(workflow.count(expression), 3)

    def test_new_items_and_organizations_get_a_generic_publisher_by_default(self) -> None:
        # Any item or organization manifest that is not specifically listed
        # in OVERRIDES must fall back to a real, generic publisher script
        # rather than being silently dropped from the menu (script=None).
        # This is what lets a brand-new item or organization be published
        # without anyone writing a new Python script.
        item_kind, item_script = publish_menu.FOLDER_ROUTES["approved_items"]
        org_kind, org_script = publish_menu.FOLDER_ROUTES["approved_organizations"]
        self.assertEqual(item_kind, "item")
        self.assertEqual(org_kind, "organization")
        self.assertIsNotNone(item_script)
        self.assertIsNotNone(org_script)
        self.assertTrue((REPOSITORY_ROOT / item_script).is_file())
        self.assertTrue((REPOSITORY_ROOT / org_script).is_file())

    def test_workflow_clears_stale_receipts_before_publication(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "publish-approved.yml"
        ).read_text()
        clear = "find receipts -maxdepth 1 -type f -name '*.json' -delete"
        publish = 'python scripts/publish_selected.py --subject "$PUBLISH_SUBJECT"'
        self.assertIn(clear, workflow)
        self.assertLess(workflow.index(clear), workflow.index(publish))


if __name__ == "__main__":
    unittest.main()
