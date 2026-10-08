"""Stable T1–T5 dictionary representation, including legacy name-only data."""

from uuid import NAMESPACE_URL, uuid5


DIMENSIONS = tuple(f"T{number}" for number in range(1, 6))


def legacy_tag_id(dimension: str, name: str) -> str:
    return f"{dimension}-{uuid5(NAMESPACE_URL, f'strat-matrix:tag:{dimension}:{name}').hex.upper()}"


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
                items.append({"id": value["id"], "name": value["name"],
                              "enabled": bool(value["enabled"])})
        result[dimension] = items
    return result


def active_tag_names(items: dict[str, list[dict]]) -> dict[str, list[str]]:
    return {dimension: [item["name"] for item in items[dimension] if item["enabled"]]
            for dimension in DIMENSIONS}


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
                      for item in snapshot[dimension] if item["name"] == name}
        if len(candidates) == 1:
            resolved[dimension] = candidates.pop()
    return resolved
