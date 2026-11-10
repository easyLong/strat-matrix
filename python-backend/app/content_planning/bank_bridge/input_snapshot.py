"""Freeze source facts before planner write transactions acquire local locks."""
from .bridge import collect
from .contracts import AccountQuery, TopicQuery
from contextlib import contextmanager
from .factory import get_source, source_mode, use_adapters
from .memory import MemorySource


def freeze_inputs(account_ids, topic_ids):
    source = get_source(None)
    accounts, topics = [], []
    for identifiers, method, query_type, result in (
        (None if account_ids is None else sorted(set(account_ids)), 'accounts', AccountQuery, accounts),
        (None if topic_ids is None else sorted(set(topic_ids)), 'topics', TopicQuery, topics),
    ):
        key = 'account_ids' if method == 'accounts' else 'topic_ids'
        if identifiers is None:
            result.extend(collect(source, method, query_type()))
            continue
        for offset in range(0, len(identifiers), 500):
            result.extend(collect(source, method, query_type(**{key: identifiers[offset:offset + 500]})))
    # This generic in-memory adapter contains actual queried DTOs, not fabricated fixtures.
    return MemorySource([a.model_copy(deep=True) for a in accounts],
                        [t.model_copy(deep=True) for t in topics])


@contextmanager
def frozen_java_inputs(*, account_ids=(), topic_ids=(), needed=True):
    """Enter before a write transaction; None means all records, () means none."""
    if not needed or source_mode() != 'java_http':
        yield
        return
    source = freeze_inputs(account_ids, topic_ids)
    with use_adapters(source):
        yield
