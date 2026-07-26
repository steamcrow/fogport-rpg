import importlib.util
import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


sys.modules.setdefault("requests", types.SimpleNamespace())
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_fogport_world_map.py"
SPEC = importlib.util.spec_from_file_location("publish_fogport_world_map", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class FogportWorldMapTests(unittest.TestCase):
    def test_exact_one_is_case_insensitive(self):
        result = MODULE.exact_one(
            [{"id": 7, "name": "Fogport"}, {"id": 8, "name": "Nine Spoons"}],
            "fogport",
            "location",
        )
        self.assertEqual(result["id"], 7)

    def test_exact_one_rejects_ambiguity(self):
        with self.assertRaises(SystemExit):
            MODULE.exact_one(
                [{"id": 7, "name": "Fogport"}, {"id": 8, "name": "FOGPORT"}],
                "Fogport",
                "location",
            )

    def test_headers_do_not_claim_json_for_multipart(self):
        self.assertNotIn("Content-Type", MODULE.headers("secret"))
        self.assertEqual(
            MODULE.headers("secret", json_body=True)["Content-Type"],
            "application/json",
        )

    def test_validate_manifest_rejects_image_over_kanka_limit(self):
        with tempfile.TemporaryDirectory(dir=MODULE.ROOT) as directory:
            root = Path(directory)
            image = root / "map.jpg"
            image.write_bytes(b"x" * (MODULE.KANKA_MAX_IMAGE_BYTES + 1))
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "campaign_id": MODULE.CAMPAIGN_ID,
                        "campaign_name": MODULE.CAMPAIGN_NAME,
                        "image_path": str(image.relative_to(MODULE.ROOT)),
                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                        "approval": {
                            "status": "approved",
                            "approved_by": "Daniel Davis",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SystemExit, "3072 KB upload limit"):
                MODULE.validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
