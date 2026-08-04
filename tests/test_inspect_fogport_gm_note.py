from __future__ import annotations

import unittest

from scripts.inspect_fogport_gm_note import (
    CAMPAIGN_ID,
    TARGET_ENTITY_ID,
    select_target,
)


class InspectFogportGmNoteTests(unittest.TestCase):
    def test_operation_is_locked_to_exact_fogport_entity(self) -> None:
        self.assertEqual(CAMPAIGN_ID, 410879)
        self.assertEqual(TARGET_ENTITY_ID, 9626686)

    def test_select_target_requires_one_exact_entity_id(self) -> None:
        expected = {"id": 44, "entity_id": TARGET_ENTITY_ID, "name": "GM"}
        self.assertEqual(select_target([expected]), expected)
        with self.assertRaises(SystemExit):
            select_target([])
        with self.assertRaises(SystemExit):
            select_target([expected, dict(expected)])


if __name__ == "__main__":
    unittest.main()
