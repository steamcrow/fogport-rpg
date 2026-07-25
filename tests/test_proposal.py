import unittest

from kanka_librarian.proposal import ProposalError, build_proposal


SNAPSHOT = {
    "campaign": {"id": 29474},
    "locations": [
        {"name": "Nine Spoons", "entity_id": 9001},
        {"name": "The Docks", "entity_id": 9002},
    ],
    "characters": [{"name": "Mercy", "entity_id": 8001}],
}


class ProposalTests(unittest.TestCase):
    def test_existing_inline_reference_gets_real_id(self):
        result = build_proposal(SNAPSHOT, {"changes": [{
            "temp_id": "byl",
            "action": "update",
            "section": "characters",
            "name": "Byl Häsbaine",
            "entry": "Byl is from Nine Spoons.",
            "references": [{"name": "Nine Spoons", "section": "locations"}],
        }]})
        proposal = result["proposals"][0]
        self.assertEqual(
            proposal["rendered_entry"],
            "Byl is from [entity:9001|Nine Spoons].",
        )
        self.assertFalse(proposal["blocked"])
        self.assertFalse(result["kanka_writes_performed"])

    def test_forward_reference_waits_for_create(self):
        result = build_proposal(SNAPSHOT, {"changes": [
            {
                "temp_id": "fogport",
                "action": "create",
                "section": "locations",
                "name": "Fogport",
            },
            {
                "temp_id": "eel",
                "action": "create",
                "section": "locations",
                "name": "Twisted Eel",
                "parent_temp_id": "spoons",
            },
            {
                "temp_id": "spoons",
                "action": "create",
                "section": "locations",
                "name": "New Nine Spoons",
                "parent_temp_id": "fogport",
                "entry": "A district of Fogport.",
                "references": [
                    {"name": "Fogport", "section": "locations"},
                ],
            },
        ]})
        self.assertEqual(result["create_order"], ["fogport", "spoons", "eel"])
        reference = result["proposals"][2]["resolved_references"][0]
        self.assertEqual(reference["status"], "pending_create")
        self.assertNotIn("[entity:", result["proposals"][2]["rendered_entry"])

    def test_unresolved_reference_is_blocked(self):
        result = build_proposal(SNAPSHOT, {"changes": [{
            "temp_id": "unknown",
            "action": "update",
            "section": "characters",
            "name": "Someone",
            "entry": "They came from Nowhere.",
            "references": [{"name": "Nowhere", "section": "locations"}],
        }]})
        self.assertTrue(result["proposals"][0]["blocked"])
        self.assertEqual(result["approval_questions"][0]["reason"], "no_exact_match_or_approved_create")

    def test_dependency_cycle_is_rejected(self):
        with self.assertRaises(ProposalError):
            build_proposal(SNAPSHOT, {"changes": [
                {"temp_id": "a", "action": "create", "section": "locations", "name": "A", "parent_temp_id": "b"},
                {"temp_id": "b", "action": "create", "section": "locations", "name": "B", "parent_temp_id": "a"},
            ]})


if __name__ == "__main__":
    unittest.main()
