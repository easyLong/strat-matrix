"""Read business-owned production usage through Java; keep legacy reads for old snapshots/tests."""
from .contracts import UsageOutput, UsageQuery
from .factory import source_mode
from .java_http import JavaHTTPClient


def current_counts(identifiers):
    from ..system_config import get_setting, snapshot
    values = snapshot()
    if 'PLANNING_ENV' not in values:
        return None
    if source_mode() == 'java_http':
        client = JavaHTTPClient.from_settings()
    else:
        root = get_setting('JAVA_GATEWAY_URL', '').rstrip('/') or 'http://127.0.0.1:6931'
        client = JavaHTTPClient(root + '/api/plan', get_setting('INTEGRATION_TOKEN'),
                                routes={'official_usage': 'query/topic-usage'})
    response = client.read('official_usage', UsageQuery(topic_ids=identifiers), UsageOutput)
    records = response.topic_results
    if {row.topic_id for row in records} != set(identifiers) or len(records) != len(identifiers):
        from .ports import DataContractError
        raise DataContractError('Java使用次数查询未完整返回所请求的选题')
    return {row.topic_id: row.official_use_count for row in records}
