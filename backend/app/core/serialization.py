from datetime import datetime, timezone
import json
from typing import Any
from pydantic import BaseModel

def utc_naive(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value else None

def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

def source_record_json(record: BaseModel, added_fields: set[str]) -> str:
    """Keep retries from older clients byte-identical after optional fields are added."""
    absent = added_fields - record.model_fields_set
    return as_json(record.model_dump(mode="json", exclude=absent))

def single_choice_labels(tags: dict) -> dict[str, str] | None:
    if not isinstance(tags, dict):
        return None
    labels: dict[str, str] = {}
    for index in range(1, 7):
        value = tags.get(f"T{index}", tags.get(f"t{index}"))
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if not isinstance(value, str) or not value.strip() or len(value) > 80:
            return None
        labels[f"t{index}"] = value.strip()
    return labels
