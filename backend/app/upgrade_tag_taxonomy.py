"""Initialize the reviewed two-level dictionary without replacing legacy topic labels.

Run once with python -m app.upgrade_tag_taxonomy. Existing grouped dictionaries
are left intact; the normal versioned save operation records the migration.
"""
import json
from pathlib import Path
from .integration import TagTaxonomyInput, get_tag_taxonomy, put_tag_taxonomy


def upgrade() -> dict:
    current = get_tag_taxonomy()
    existing = current["items"]
    if any(item.get("node_type") == "group" for dimension in ("T3", "T4", "T5")
           for item in existing.get(dimension, [])):
        return {"changed": False, "version": current["version"]}
    catalog_path = Path(__file__).resolve().parents[2] / "frontend/src/data/topicTaxonomy.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    items = {}
    for dimension, names in (("T1", ("非营销", "营销")), ("T2", ("流量", "转化"))):
        items[dimension] = existing.get(dimension) or [{"name": name, "enabled": True} for name in names]
    for dimension in ("T3", "T4", "T5"):
        items[dimension] = []
        old = {item["name"]: item for item in existing.get(dimension, [])}
        matched = set()
        for index, category in enumerate(catalog[dimension]):
            key = f"initial-{dimension}-{index}"
            items[dimension].append({"name": category["name"], "enabled": True, "node_type": "group", "client_id": key})
            for name in category["tags"]:
                value = dict(old[name]) if name in old else {"name": name, "enabled": True}
                value.update(node_type="tag", parent_id=key)
                items[dimension].append(value)
                matched.add(name)
        legacy = [dict(item) for name, item in old.items() if name not in matched]
        if legacy:
            key = f"initial-{dimension}-legacy"
            items[dimension].append({"name": "待归类", "enabled": True, "node_type": "group", "client_id": key})
            for item in legacy:
                item.update(node_type="tag", parent_id=key)
            items[dimension].extend(legacy)
    result = put_tag_taxonomy(TagTaxonomyInput(items=items, expected_version=current["version"]))
    return {"changed": True, "version": result["version"],
            "dimensions": {dimension: len(result["items"][dimension]) for dimension in items}}


if __name__ == "__main__":
    print(json.dumps(upgrade(), ensure_ascii=True))
