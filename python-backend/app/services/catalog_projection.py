"""Shared lifecycle and label projection. Scoped in-memory inputs do not read fixtures or Java."""
import hashlib
from ..bank_bridge.bridge import account_options, topic_options
from ..bank_bridge.factory import use_adapters
from ..bank_bridge.memory import MemorySource
from ..db import connection
from .configuration import get_config
from .catalog import attach_topic_labels


def project_catalog(accounts, topics, *, available_only=True):
    config = get_config()
    source = MemorySource(accounts=accounts, topics=topics)
    with use_adapters(source), connection() as db, db.cursor() as cursor:
        account_rows = account_options(cursor, config.config, limit=1000) if accounts else []
        topic_rows = topic_options(cursor, limit=1000, available_only=available_only) if topics else []
        attach_topic_labels(cursor, topic_rows)
        for row in topic_rows:
            row.pop('topic_payload', None)
            row.pop('_catalog_topic', None)
    version = hashlib.sha256(config.config.model_dump_json().encode()).hexdigest()
    return dict(accounts=account_rows, topics=topic_rows, algorithm_version=version)
