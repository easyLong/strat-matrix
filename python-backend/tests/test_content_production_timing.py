import json

import pytest
from fastapi import HTTPException

from app.content_planning.algorithm_config_commands import BUSINESS_FIELDS
from app.content_planning.business_snapshot import normalize_business_snapshot


def business_config():
    return dict(planning_days=[1, 3, 5], schedule_day=2, schedule_time='22:00',
                marketing_max=1, hotspot_ratio=20)


def test_old_business_snapshots_keep_their_original_payload_and_new_timing_is_frozen():
    original = business_config()
    _, frozen = normalize_business_snapshot(1, original)
    assert json.loads(frozen) == original
    timing = dict(ordinary=3, marketing=0, hotspot=1)
    _, frozen = normalize_business_snapshot(2, {**original, 'content_production_lead_days': timing})
    assert json.loads(frozen)['content_production_lead_days'] == timing
    assert 'content_production_lead_days' in BUSINESS_FIELDS


@pytest.mark.parametrize('timing', [dict(ordinary=-1), dict(hotspot=366), dict(marketing=1.5),
                                   dict(ordinary=True), dict(unknown=3)])
def test_invalid_production_timing_is_rejected(timing):
    with pytest.raises(HTTPException) as error:
        normalize_business_snapshot(2, {**business_config(), 'content_production_lead_days': timing})
    assert error.value.status_code == 422
