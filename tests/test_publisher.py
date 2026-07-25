import unittest

from kanka_librarian.publisher import PublishError, apply_approved_proposal, approve_proposal


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

    def create_post(self, campaign_id, entity_id, payload):
        self.calls.append(("post", campaign_id, entity_id, payload))
        return {"id": 201}

    def create_attribute(self, campaign_id, entity_id, payload):
        self.calls.append(("attribute", campaign_id, entity_id, payload))
        return {"id": 202}

    def create_relation(self, campaign_id, entity_id, payload):
        self.calls.append(("relation", campaign_id, entity_id, payload))
        return {"id": 203}


def proposal():
    return {
        "schema_version": 1, "mode": "proposal-only", "campaign_id": 29474,
        "create_order": ["fogport", "spoons", "byl"], "approval_questions": [],
        "proposals": [
            {"temp_id": "fogport", "action": "create", "section": "locations", "name": "Test World", "entry": "", "resolved_references": [], "blocked": False},
            {"temp_id": "spoons", "action": "create", "section": "locations", "name": "Nine Spoons", "parent_temp_id": "fogport", "entry": "A district of Test World.", "resolved_references": [{"name": "Test World", "phrase": "Test World", "status": "pending_create", "temp_id": "fogport"}], "blocked": False},
            {"temp_id": "byl", "action": "create", "section": "characters", "name": "Byl Häsbaine", "entry": "Byl is from Nine Spoons.", "resolved_references": [{"name": "Nine Spoons", "phrase": "Nine Spoons", "status": "pending_create", "temp_id": "spoons"}], "posts": [{"name": "GM Plans", "entry": "Secret future.", "is_private": True}], "attributes": [{"name": "Origin", "value": "Nine Spoons", "is_private": False}], "relationships": [{"relation": "is from", "target_temp_id": "spoons", "is_private": False}], "blocked": False},
        ],
    }


class PublisherTests(unittest.TestCase):
    def test_dry_run_makes_no_writes_and_counts_dependents(self):
        writer = FakeWriter()
        result = apply_approved_proposal(approve_proposal(proposal(), approved_by="Daniel"), writer)
        self.assertFalse(result["kanka_writes_performed"])
        self.assertEqual(writer.calls, [])
        self.assertEqual((result["posts_planned"], result["attributes_planned"], result["relationships_planned"]), (1, 1, 1))

    def test_two_pass_publish_uses_real_ids_and_parent_order(self):
        writer = FakeWriter()
        result = apply_approved_proposal(approve_proposal(proposal(), approved_by="Daniel"), writer, execute=True)
        self.assertTrue(result["kanka_writes_performed"])
        self.assertEqual([call[0] for call in writer.calls[:3]], ["create"] * 3)
        self.assertEqual(writer.calls[1][3]["parent_id"], 1101)
        self.assertIn("[entity:1102|Nine Spoons]", writer.calls[5][4]["entry"])

    def test_dependents_publish_after_entity_pass_and_keep_privacy(self):
        writer = FakeWriter()
        apply_approved_proposal(approve_proposal(proposal(), approved_by="Daniel"), writer, execute=True)
        post, attribute, relation = writer.calls[-3:]
        self.assertEqual([post[0], attribute[0], relation[0]], ["post", "attribute", "relation"])
        self.assertTrue(post[3]["is_private"])
        self.assertEqual(attribute[3]["name"], "Origin")
        self.assertEqual(relation[3]["target_id"], 1102)

    def test_existing_entity_dependents_require_entity_id(self):
        bad = proposal()
        bad["proposals"][2]["action"] = "update"
        bad["proposals"][2]["kanka_id"] = 77
        bad["create_order"].remove("byl")
        with self.assertRaises(PublishError):
            apply_approved_proposal(approve_proposal(bad, approved_by="Daniel"), FakeWriter(), execute=True)

    def test_edit_after_approval_is_rejected(self):
        approved = approve_proposal(proposal(), approved_by="Daniel")
        approved["proposals"][0]["name"] = "Changed afterward"
        with self.assertRaises(PublishError):
            apply_approved_proposal(approved, FakeWriter(), execute=True)

    def test_unresolved_or_delete_is_rejected(self):
        bad = proposal()
        bad["proposals"][0]["action"] = "delete"
        with self.assertRaises(PublishError):
            apply_approved_proposal(approve_proposal(bad, approved_by="Daniel"), FakeWriter(), execute=True)

    def test_fogport_campaign_is_never_writable(self):
        bad = proposal()
        bad["campaign_id"] = 410879
        with self.assertRaises(PublishError):
            apply_approved_proposal(approve_proposal(bad, approved_by="Daniel"), FakeWriter(), execute=True)


if __name__ == "__main__":
    unittest.main()
