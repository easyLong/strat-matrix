"""Development-only frozen fixtures; no synchronization or shadow database tables."""

import json
from pathlib import Path

from .contracts import Account, Topic
from .memory import MemorySource
from .ports import IntegrationUnavailable

def load_fixture(path=None):
    if path is None:
        from ..resources import fixture_path
        path = fixture_path()
    path = Path(path)
    if not path.is_file():
        raise IntegrationUnavailable('本地测试夹具不存在；请配置行内 SQL，或显式准备开发测试数据')
    raw = json.loads(path.read_text(encoding='utf-8'))
    def restore(model, item):
        result = model.model_validate(item['data'])
        result._local_payload = item.get('local_payload', {})
        return result
    return MemorySource(accounts=[restore(Account, a) for a in raw['accounts']],
                        topics=[restore(Topic, t) for t in raw['topics']])
