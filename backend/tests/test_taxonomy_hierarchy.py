"""Compatibility and selection boundaries for the two-level label dictionary."""
import unittest

from pydantic import ValidationError

from app.integration import TagTaxonomyInput
from app.taxonomy import active_tag_names, legacy_tag_ids, normalize_taxonomy, selectable_tags


class TaxonomyHierarchyTests(unittest.TestCase):
    def test_groups_are_not_labels_and_disabled_parent_blocks_descendants(self):
        items = [
            {"id": "g", "name": "金融与财富", "enabled": False, "node_type": "group"},
            {"id": "leaf", "name": "信用卡", "enabled": True, "parent_id": "g"},
            {"id": "old", "name": "历史标签", "enabled": True},
        ]
        self.assertEqual([item["id"] for item in selectable_tags(items)], ["old"])
        items[0]["enabled"] = True
        self.assertEqual([item["id"] for item in selectable_tags(items)], ["leaf", "old"])

    def test_legacy_names_keep_identity_and_category_metadata_survives(self):
        old = normalize_taxonomy({"T3": ["信用卡"]})
        revised = normalize_taxonomy({"T3": [
            {"id": "g", "name": "金融与财富", "enabled": True, "node_type": "group"},
            {**old["T3"][0], "parent_id": "g"},
        ]})
        self.assertEqual(revised["T3"][1]["id"], old["T3"][0]["id"])
        self.assertEqual(revised["T3"][1]["parent_id"], "g")
        self.assertEqual(active_tag_names(revised)["T3"], ["信用卡"])

    def test_backfill_does_not_resolve_to_a_same_named_category(self):
        snapshot = normalize_taxonomy({"T3": [
            {"id": "group", "name": "本地生活", "enabled": True, "node_type": "group"},
            {"id": "legacy-leaf", "name": "本地生活", "enabled": True},
        ]})
        self.assertEqual(legacy_tag_ids({"T3": "本地生活"}, [snapshot]), {"T3": "legacy-leaf"})

    def test_input_rejects_third_level_and_grouped_fixed_enumerations(self):
        base = {dimension: [{"name": "值", "enabled": True}] for dimension in ("T1", "T2", "T3", "T4", "T5")}
        with self.assertRaises(ValidationError):
            TagTaxonomyInput(items={**base, "T3": [{"name": "三级分类", "node_type": "group", "parent_id": "parent"}]})
        with self.assertRaises(ValidationError):
            TagTaxonomyInput(items={**base, "T1": [{"name": "错误分类", "node_type": "group"}]})


if __name__ == "__main__":
    unittest.main()
