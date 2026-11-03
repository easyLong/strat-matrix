"""Development-only frozen fixtures; no synchronization or shadow database tables."""

import json
from pathlib import Path

from .contracts import Account, Topic
from .memory import MemorySource
from .ports import IntegrationUnavailable

FIXTURE_PATH = Path(__file__).resolve().parents[3] / 'run/bank-source-fixture.json'


def load_fixture(path=None):
    path = path or FIXTURE_PATH
    if not path.is_file():
        raise IntegrationUnavailable('本地测试夹具不存在；请配置行内 SQL，或显式准备开发测试数据')
    raw = json.loads(path.read_text(encoding='utf-8'))
    def restore(model, item):
        result = model.model_validate(item['data'])
        result._local_payload = item.get('local_payload', {})
        return result
    return MemorySource(accounts=[restore(Account, a) for a in raw['accounts']],
                        topics=[restore(Topic, t) for t in raw['topics']])
