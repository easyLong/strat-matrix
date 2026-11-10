"""One bounded pass of each persisted queue; timing belongs to the Java host."""
from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from ..ordinary_scheduler import run_due as weekly, schedule_owner
from ..hotspot_scheduler import run_due as hotspot
from ..planning_workflow_worker import run_once as planning
from ..services.manual_tasks import run_once as manual
from ..manual_compute import run_once as manual_compute

LOG = logging.getLogger('application-worker')
def manual_pass():
    return {'status': 'delegated_to_java'} if schedule_owner() == 'java' else manual()

def planning_pass():
    return planning(process_content=schedule_owner() != 'java')

JOBS = {'manual': (2, manual_pass), 'planning': (10, planning_pass), 'weekly': (60, weekly), 'hotspot': (60, hotspot)}
JOBS['manual_compute'] = (2, manual_compute)


def execute(name, handler):
    try:
        result = handler(datetime.now(ZoneInfo('Asia/Shanghai'))) if name in ('weekly', 'hotspot') else handler()
        failed = isinstance(result, dict) and (result.get('status') in ('failed', 'error') or result.get('failed', 0)
                  or any(row.get('error') or row.get('http_error') or row.get('status') == 'failed'
                         for row in result.get('pipelines', [])))
        return {'status': 'failed' if failed else 'ok', 'result': result}
    except Exception as exc:
        LOG.exception('Background job %s failed: %s', name, type(exc).__name__)
        return {'status': 'failed', 'error_type': type(exc).__name__}


def run_once(jobs=None):
    selected = JOBS if jobs is None else jobs
    return {name: execute(name, handler) for name, (_, handler) in selected.items()}
