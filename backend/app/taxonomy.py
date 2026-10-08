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
