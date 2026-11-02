"""Copy to site_sql_private.py INSIDE the bank, then fill only approved SQL/mappers.

The private file is ignored by Git. All SQL uses named bound parameters.
Rows may use Chinese DTO aliases or the Python property names in contracts.py.
No credentials, bank table names, or real records belong in this template.

Parameters common to page SQL: limit, offset, updated_from, updated_to.
IDs: all_accounts / all_topics indicate no ID filter; {{account_ids}} and
{{topic_ids}} are expanded into bound placeholders, never interpolated values.
Account posts: {{account_ids}}, history_from, history_to (only this page's IDs).
Topic page: source, topic_type, available_only, valid_at.
Marketing page: account_id. Query only approved, undated content and sort by
approved_at ASC, content_id ASC. Effective placement: account_id, publish_date.
Count and row SQL must use exactly the same eligibility/time filters.
Use ORDER BY account ID / topic ID for stable pagination. Do not page joins
against one-to-many tables; load a page of parent IDs before fetching children.
"""

ACCOUNT_COUNT = None
ACCOUNT_ROWS = None
ACCOUNT_POSTS = None
TOPIC_COUNT = None
TOPIC_ROWS = None
MARKETING_COUNT = None
MARKETING_ROWS = None
EFFECTIVE_MARKETING_ROWS = None


def map_account(row):
    """Map bank enums/columns to Account fields. Exclude interaction rows here."""
    return row


def map_interaction(row):
    return row


def map_topic(row):
    return row


def map_marketing_content(row):
    return row


def map_effective_placement(row):
    return row


def production_results(cursor, query):
    """Return ProductionRecord entries carrying slot_id AND version."""
    from .ports import IntegrationUnavailable
    raise IntegrationUnavailable('IF-04：生产审核结果读取方法尚未实现')
