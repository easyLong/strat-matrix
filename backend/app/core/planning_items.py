"""Pure plan presentation and replacement eligibility shared by all scopes."""
import json
from ..planning_progress import production_status
def infer_content_role(row: dict, topic: dict) -> str:
    """Use the topic/slot business role for local demo data."""
    if topic.get('business_role'):
        return str(topic['business_role'])
    if row.get('slot_type') == 'marketing_priority' or topic.get('is_marketing'):
        return '转化'
    return '流量'

def replacement_block_reason(row: dict, plan_type: str | None = None) -> str:
    if plan_type not in ("auto", "manual"):
        return "当前策划类型不支持替换"
    if not row.get("topic_id"):
        return "热点空槽待确定选题"
    if not row.get("slot_id") or row.get("version") is None:
        return "状态暂无法确认，不允许替换"
    if "slot_topic_id" in row and row["slot_topic_id"] != row["topic_id"]:
        return "当前结果与槽位状态不一致，请刷新后重试"
    if (row.get("published_at") is not None or row.get("status") == "已发布"
            or row.get("production_status") in ("published", "已发布")):
        return "内容已发布，当前结果不可替换"
    if production_status(row) == "ready":
        return "内容生产中，选题不可替换"
    if production_status(row) == "generated":
        return "内容已完成，选题不可替换"
    return ""

def enrich_plan_item(row: dict, plan_type: str | None = None) -> dict:
    source_payload = row.pop("topic_payload", None)
    source = {}
    if source_payload and row.get("topic_type") not in ("营销", "热点"):
        try:
            source = json.loads(source_payload)
            if not isinstance(source, dict):
                source = {}
        except (TypeError, json.JSONDecodeError):
            source = {}
    row["content_type"] = row.get("content_type") or source.get("content_type", "")
    row["outline"] = row.get("outline") or source.get("outline", "") or source.get("summary", "")
    if not row.get("topic_type") and row.get("topic_id"):
        row["topic_type"] = (
            "热点" if row.get("slot_type") == "hotspot" else
            "营销" if row.get("slot_type") == "marketing_priority" or
            source.get("is_marketing") or row.get("source_is_marketing") else "普通"
        )
    row["content_role"] = row.get("content_role") or infer_content_role(row, source if source_payload else {})
    row["production_status"] = production_status(row)
    published_at = row.get("published_at")
    block_reason = replacement_block_reason(row, plan_type)
    allow = not block_reason
    publish_status = ("待确定选题" if not row.get("topic_id") else
                      "已发布" if (published_at or row.get("status") == "已发布"
                                   or row.get("production_status") in ("published", "已发布"))
                      else "未发布")
    row["publish_status"] = publish_status
    row["allow_replace"] = allow
    row["replace_block_reason"] = block_reason
    row["result_version"] = row.get("version")
    row.pop("published_at", None)
    row.pop("version", None)
    return row
