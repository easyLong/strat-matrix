"""The same synthetic source-wire fixture is asserted by Java field-mapping tests."""
import json
from pathlib import Path
import pytest
from pydantic import TypeAdapter
from app.content_planning.bank_bridge.contracts import (Account, Topic, MarketingContent, Page,
                                      EffectivePlacement, ProductionRecord, MarketingProductionRecord)

FIXTURE = Path(__file__).resolve().parents[2] / 'java-backend/godp-planning-server/src/test/resources/bank-source/contract-sample.json'


@pytest.mark.parametrize('capability,model', [
    ('accounts', Page[Account]), ('topics', Page[Topic]),
    ('marketing-contents', Page[MarketingContent]),
    ('effective-marketing', list[EffectivePlacement]),
    ('production-status', list[ProductionRecord]),
    ('marketing-status', list[MarketingProductionRecord]),
])
def test_java_bank_source_fixture_matches_python_models(capability, model):
    payload = json.loads(FIXTURE.read_text(encoding='utf-8'))
    parsed = TypeAdapter(model).validate_python(payload[capability])
    assert parsed is not None
