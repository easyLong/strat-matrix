from copy import deepcopy
from datetime import datetime,timezone

from testing.account_fixtures import complete_account


def test_complete_account_keeps_known_facts_and_adds_valid_interaction_examples():
    source=dict(account_id='E2E-A',nickname='测试甲',followers=0,eligible=False,gender='女',persona='车圈达人')
    original=deepcopy(source)
    now=datetime(2026,11,3,tzinfo=timezone.utc)
    result=complete_account(source,now=now)
    assert source==original
    assert result['followers']==0 and result['eligible'] is False and result['gender']=='女'
    assert all(result[key] for key in ('owner_um','organization','platform','account_type','interests','expression_style','updated_at'))
    assert len(result['interactions'])==4
    assert complete_account(result,now=now)==result


def test_account_contract_accepts_the_completed_fixture():
    from app.content_planning.bank_bridge.contracts import Account
    account=Account.model_validate(complete_account(dict(account_id='E2E-B',persona='家庭理财分享者',followers=120)))
    assert len(account.interactions)==12
    assert all(p.title and p.likes is not None and p.favorites is not None and p.comments is not None for p in account.interactions)


def test_page_account_dto_preserves_the_completed_persona_and_interaction_fields():
    from unittest.mock import patch
    from app.content_planning.bank_bridge.bridge import account_options
    from app.content_planning.bank_bridge.memory import MemorySource
    from app.content_planning.models import StrategyConfig,AccountOption
    source=MemorySource(accounts=[complete_account(dict(account_id='E2E-C',persona='家庭理财分享者'))])
    with patch('app.content_planning.bank_bridge.bridge.get_source',return_value=source):
        rows=account_options(None,StrategyConfig())
    account=AccountOption.model_validate(rows[0])
    assert account.gender and account.interests and account.expression_style and account.updated_at
    assert len(account.interaction_data)==4
