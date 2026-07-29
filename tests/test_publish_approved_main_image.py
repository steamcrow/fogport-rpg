import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_approved_main_image.py"
SPEC = importlib.util.spec_from_file_location("publish_approved_main_image", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ApprovedMainImageTests(unittest.TestCase):
    def test_publisher_starts_with_workflow_command(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "scripts/publish_approved_main_image.py", "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        self.assertIn("--receipt", completed.stdout)

    def test_bellworks_manifest_is_locked_to_existing_entity_and_artwork(self):
        root = Path(__file__).resolve().parents[1]
        manifest_path = root / "kanka_librarian/approved_images/bellworks.json"
        document, image_bytes, image_name = MODULE.load_approval(manifest_path)
        self.assertEqual(document["campaign_id"], 410879)
        self.assertEqual(document["entity_id"], 9637931)
        self.assertEqual(document["entity_name"], "The Bellworks")
        self.assertEqual(
            hashlib.sha256(image_bytes).hexdigest(),
            document["sha256"],
        )
        self.assertEqual(image_name, "bellworks-fog-factories-approved.jpg")

    def test_rejects_changed_artwork(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "changed.jpg"
            image.write_bytes(b"changed")
            manifest = root / "approval.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": 410879,
                        "campaign_name": "Fogport",
                        "entity_id": 9637931,
                        "entity_name": "The Bellworks",
                        "repository_path": "changed.jpg",
                        "sha256": "0" * 64,
                        "approval": {"status": "approved"},
                    }
                ),
                encoding="utf-8",
            )
            original_root = MODULE.REPOSITORY_ROOT
            MODULE.REPOSITORY_ROOT = root
            try:
                with self.assertRaisesRegex(SystemExit, "SHA-256 mismatch"):
                    MODULE.load_approval(manifest)
            finally:
                MODULE.REPOSITORY_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
