from datetime import date

from fastapi import HTTPException
import pytest

from app import planning_pipeline_api as api
from app import ordinary_scheduler
from app.ordinary_planning import PlanningError

BUSINESS = dict(planning_days=[1, 3, 5], schedule_day=2, schedule_time='22:00',
                marketing_max=3, hotspot_ratio=20)

def auto_request():
    return api.AutoStart(cycle_start=date(2026, 11, 9),
                         business_config_version=7, business_config=BUSINESS)


def test_java_supplies_cycle_but_python_selects_policy(monkeypatch):
    seen = []

    def start(cycle, **kwargs):
        seen.append((cycle, kwargs))
        return {"status": "created", "pipeline_id": 42}

    monkeypatch.setattr(api, "start_v2_pipeline", start)
    result = api.start_auto_algorithm(auto_request())
    assert seen == [(date(2026, 11, 9), dict(commit_owner='java',
                    business_config_version=7, business_config=BUSINESS))]
    assert result == {"status": "created", "pipeline_id": 42}


def test_invalid_algorithm_configuration_is_explicit(monkeypatch):
    def reject(_cycle, **_kwargs):
        raise PlanningError("策略尚未批准")

    monkeypatch.setattr(api, "start_v2_pipeline", reject)
    with pytest.raises(HTTPException) as error:
        api.start_auto_algorithm(auto_request())
    assert error.value.status_code == 422


def test_python_weekly_job_does_not_compete_with_java_schedule(monkeypatch):
    monkeypatch.setattr(ordinary_scheduler, "get_setting", lambda key, default="": "java")
    monkeypatch.setattr(ordinary_scheduler, "due_cycle", lambda _now: pytest.fail("old scheduler ran"))
    assert ordinary_scheduler.run_due(None) == {"status": "delegated_to_java"}


def test_missing_new_owner_setting_keeps_existing_scheduler(monkeypatch):
    from app.system_config import SystemConfigError

    def missing(_key, _default=""):
        raise SystemConfigError("系统配置 AUTO_SCHEDULE_OWNER 尚未初始化")

    monkeypatch.setattr(ordinary_scheduler, "get_setting", missing)
    assert ordinary_scheduler.schedule_owner() == "python"

def test_java_owner_disables_old_hotspot_business_writes(monkeypatch):
    from app import hotspot_scheduler
    monkeypatch.setattr(ordinary_scheduler, 'schedule_owner', lambda: 'java')
    monkeypatch.setattr(hotspot_scheduler, '_run_due', lambda _now: pytest.fail('old hotspot business writes'))
    assert hotspot_scheduler.run_due()['status'] == 'delegated'

def test_java_owner_keeps_python_execution_algorithm_only(monkeypatch):
    from app.jobs import handlers
    monkeypatch.setattr(handlers, 'schedule_owner', lambda: 'java')
    monkeypatch.setattr(handlers, 'manual', lambda: pytest.fail('old manual writer'))
    seen=[]
    monkeypatch.setattr(handlers, 'planning', lambda **kw: seen.append(kw))
    assert handlers.manual_pass()['status'] == 'delegated_to_java'
    handlers.planning_pass()
    assert seen == [{'process_content': False}]
