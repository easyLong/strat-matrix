"""Tables retired by the shared-bank-database architecture. Never create anew."""

RETIRED_TABLES = (
    'godp_account', 'godp_topic', 'godp_account_source', 'godp_topic_source',
    'godp_marketing_topic_source', 'godp_hotspot_topic_source',
    'godp_source_sync_run', 'godp_marketing_sync_run', 'godp_hotspot_sync_run',
    'godp_content_history', 'godp_integration_outbox', 'godp_content_receipt',
    'godp_publication_receipt', 'godp_content_production_task',
)


def retired_statement(statement):
    import re
    match = re.match(r'\s*CREATE TABLE IF NOT EXISTS\s+`?(\w+)`?', statement, re.I)
    return bool(match and match.group(1) in RETIRED_TABLES)
