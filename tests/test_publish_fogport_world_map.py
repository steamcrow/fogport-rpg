import importlib.util
import sys
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


if __name__ == "__main__":
    unittest.main()
