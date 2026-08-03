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
        visible_labels = {entry["label"] for entry in visible}
        for entry in visible:
            self.assertIn(f'- "{entry["label"]}"', workflow)
        for entry in publish_menu.build_menu():
            if entry["label"] not in visible_labels:
                self.assertNotIn(f'- "{entry["label"]}"', workflow)
        self.assertIn("older_subject:", workflow)


if __name__ == "__main__":
    unittest.main()
