"""Stable T1–T5 dictionary representation, including legacy name-only data."""

from uuid import NAMESPACE_URL, uuid5
import json


DIMENSIONS = tuple(f"T{number}" for number in range(1, 6))


def legacy_tag_id(dimension: str, name: str) -> str:
    return f"{dimension}-{uuid5(NAMESPACE_URL, f'strat-matrix:tag:{dimension}:{name}').hex.upper()}"


def _tag_name(value) -> str:
    """Unwrap legacy/object-shaped names so API responses always expose text."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("name", "label", "value", "title", "text"):
            if key in value:
                return _tag_name(value[key])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value) if value is not None else ""


def normalize_taxonomy(raw: dict) -> dict[str, list[dict]]:
    """Give pre-ID tag values deterministic IDs without changing their meaning."""
    result: dict[str, list[dict]] = {}
    for dimension in DIMENSIONS:
        items = []
        for value in raw.get(dimension) or []:
            if isinstance(value, str):
                items.append({"id": legacy_tag_id(dimension, value),
                              "name": value, "enabled": True})
            else:
                name = _tag_name(value.get("name", value.get("label", value.get("value"))))
                tag_id = value.get("id") or legacy_tag_id(dimension, name)
                item = {"id": tag_id, "name": name, "enabled": bool(value.get("enabled", True))}
                if value.get("node_type") == "group" or value.get("parent_id"):
                    item.update(node_type=value.get("node_type", "tag"), parent_id=value.get("parent_id"))
                items.append(item)
        result[dimension] = items
    return result


def active_tag_names(items: dict[str, list[dict]]) -> dict[str, list[str]]:
    return {dimension: [item["name"] for item in selectable_tags(items[dimension])]
            for dimension in DIMENSIONS}


def selectable_tags(items: list[dict]) -> list[dict]:
    groups = {item["id"]: item for item in items if item.get("node_type") == "group"}
    return [item for item in items if item.get("node_type") != "group" and item["enabled"]
            and (not item.get("parent_id") or groups.get(item["parent_id"], {}).get("enabled", False))]


def tag_names_for_dimensions(tags: dict) -> dict[str, str]:
    """Read legacy scalar or one-element-list values without guessing missing tags."""
    names = {}
    for dimension in DIMENSIONS:
        value = tags.get(dimension, tags.get(dimension.lower()))
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if isinstance(value, str) and value.strip():
            names[dimension] = value.strip()
    return names


def legacy_tag_ids(tags: dict, snapshots: list[dict[str, list[dict]]]) -> dict[str, str]:
    """Backfill only unambiguous name-to-ID links from saved dictionary versions."""
    names = tag_names_for_dimensions(tags)
    resolved = {}
    for dimension, name in names.items():
        candidates = {item["id"] for snapshot in snapshots
                      for item in snapshot[dimension]
                      if item.get("node_type") != "group" and item["name"] == name}
        if len(candidates) == 1:
            resolved[dimension] = candidates.pop()
    return resolved
