"""Explicit, process-local acceptance assembly. Never imported by production startup."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    address = urlsplit(config['java_source'])
    if address.scheme != 'http' or address.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Acceptance source must be the daily loopback Java HTTP facade')
    from app.deployment_environment import current
    if current()['PLANNING_ENV'] != 'outside':
        raise ValueError('Live acceptance is outside-only')
    from app.bank_bridge import factory
    from app.bank_bridge.java_http import JavaHTTPClient, JavaHTTPSource
    from app import ordinary_scheduler
    from app.system_config import get_setting

    # Change transport/selection only. All preparation, model calls, persistence,
    # leases, V19 execution and result validation remain the production code.
    client = JavaHTTPClient.from_settings()
    if client.base_url != config['java_source']:
        raise ValueError('Acceptance must use the same Java source configuration as daily development')
    source = AcceptanceSource(JavaHTTPSource(client), config['account_id'], config['topic_ids'])
    factory.SOURCE_PROVIDER = lambda cursor: source
    original = ordinary_scheduler.get_setting
    ordinary_scheduler.get_setting = lambda key, default=None: (
        json.dumps([config['account_id']]) if key == 'AUTO_PLANNING_ACCOUNT_IDS' else original(key, default))
    from app.main import app
    from fastapi import Depends
    from app.api.security import require_integration_token
    from app.bank_bridge.contracts import AccountQuery, TopicQuery

    @app.get('/__acceptance/source-preflight', include_in_schema=False, dependencies=[Depends(require_integration_token)])
    def source_preflight():
        source=factory.get_source(None)
        accounts=source.accounts(AccountQuery(account_ids=[config['account_id']]))
        topics=source.topics(TopicQuery(page_no=2,page_size=5))
        return dict(account_count=accounts.total,topic_count=topics.total,page_items=len(topics.items))
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=config['python_port'], log_level='warning')


class AcceptanceSource:
    """Test-ID scope only; transport, DTO validation and source implementation are unchanged."""
    def __init__(self, source, account_id, topic_ids):
        self.source, self.account_id, self.topic_ids = source, account_id, list(topic_ids)

    def accounts(self, query):
        ids = [self.account_id] if query.account_ids is None else [i for i in query.account_ids if i == self.account_id]
        return self.source.accounts(query.model_copy(update={'account_ids': ids}))

    def topics(self, query):
        ids = self.topic_ids if query.topic_ids is None else [i for i in query.topic_ids if i in self.topic_ids]
        return self.source.topics(query.model_copy(update={'topic_ids': ids}))

    def marketing_contents(self, query): return self.source.marketing_contents(query)
    def effective_marketing(self, query): return self.source.effective_marketing(query)


if __name__ == '__main__':
    main()
