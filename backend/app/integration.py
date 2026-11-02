"""Compatibility exports for the current shared-database integration boundary."""
from .api.security import require_integration_token
from .api.common import db_error
from .core.serialization import utc_naive, as_json, source_record_json, single_choice_labels
from .services.planning_slots import queue_manual_slot
from .services.labels import TagTaxonomyItemInput, TagTaxonomyInput, TopicTagsInput, get_tag_taxonomy, put_tag_taxonomy, resolve_topic_tag_ids, list_topic_label_jobs, claim_topic_label_job, put_topic_tags, topic_tag_history

def queue_event(*args, **kwargs):
    return ''
