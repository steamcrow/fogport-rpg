import unittest

from kanka_librarian.publisher import (
    PublishError,
    apply_approved_proposal,
    approve_proposal,
)


class FakeWriter:
    def __init__(self):
        self.calls = []
        self.next_id = 100

    def create_entity(self, campaign_id, section, payload):
        self.calls.append(("create", campaign_id, section, payload))
        self.next_id += 1
        return {"id": self.next_id, "entity_id": self.next_id + 1000}

    def update_entity(self, campaign_id, section, kanka_id, payload):
        self.calls.append(("update", campaign_id, section, kanka_id, payload))
        return {"id": kanka_id, "entity_id": kanka_id + 1000}


def proposal():
    return {
        "schema_version": 1,
        "mode": "proposal-only",
        "campaign_id": 29474,
        "create_order": ["fogport", "spoons", "byl"],
        "approval_questions": [],
        "proposals": [
            {
                "temp_id": "fogport",
                "action": "create",
                "section": "locations",
                "name": "Test World",
                "entry": "",
                "resolved_references": [],
                "blocked": False,
            },
            {
                "temp_id": "spoons",
                "action": "create",
                "section": "locations",
                "name": "Nine Spoons",
                "parent_temp_id": "fogport",
                "entry": "A district of Test World.",
                "resolved_references": [
                    {
                        "name": "Test World",
                        "phrase": "Test World",
                        "status": "pending_create",
                        "temp_id": "fogport",
                    }
                ],
                "blocked": False,
            },
            {
                "temp_id": "byl",
                "action": "create",
                "section": "characters",
                "name": "Byl Häsbaine",
                "entry": "Byl is from Nine Spoons.",
                "resolved_references": [
                    {
                        "name": "Nine Spoons",
                        "phrase": "Nine Spoons",
                        "status": "pending_create",
                        "temp_id": "spoons",
                    }
                ],
                "blocked": False,
            },
        ],
    }


class PublisherTests(unittest.TestCase):
    def test_dry_run_makes_no_writes(self):
        writer = FakeWriter()
        result = apply_approved_proposal(
            approve_proposal(proposal(), approved_by="Daniel"), writer
        )
        self.assertFalse(result["kanka_writes_performed"])
        self.assertEqual(writer.calls, [])

    def test_two_pass_publish_uses_real_ids_and_parent_order(self):
        writer = FakeWriter()
        result = apply_approved_proposal(
            approve_proposal(proposal(), approved_by="Daniel"),
            writer,
            execute=True,
        )
        self.assertTrue(result["kanka_writes_performed"])
        self.assertEqual([call[0] for call in writer.calls[:3]], ["create"] * 3)
        spoons_shell = writer.calls[1][3]
        self.assertEqual(spoons_shell["parent_id"], 1101)
        byl_final = writer.calls[5][4]
        self.assertIn("[entity:1102|Nine Spoons]", byl_final["entry"])

    def test_edit_after_approval_is_rejected(self):
        approved = approve_proposal(proposal(), approved_by="Daniel")
        approved["proposals"][0]["name"] = "Changed afterward"
        with self.assertRaises(PublishError):
            apply_approved_proposal(approved, FakeWriter(), execute=True)

    def test_unresolved_or_delete_is_rejected(self):
        bad = proposal()
        bad["proposals"][0]["action"] = "delete"
        with self.assertRaises(PublishError):
            apply_approved_proposal(
                approve_proposal(bad, approved_by="Daniel"),
                FakeWriter(),
                execute=True,
            )

    def test_fogport_campaign_is_never_writable(self):
        bad = proposal()
        bad["campaign_id"] = 410879
        with self.assertRaises(PublishError):
            apply_approved_proposal(
                approve_proposal(bad, approved_by="Daniel"),
                FakeWriter(),
                execute=True,
            )


if __name__ == "__main__":
    unittest.main()
