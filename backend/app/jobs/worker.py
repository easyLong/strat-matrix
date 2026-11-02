"""Independent weekly, hotspot, workflow and durable manual-task polling."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import logging
from time import monotonic, sleep
from zoneinfo import ZoneInfo

from ..ordinary_scheduler import run_due as weekly
from ..hotspot_scheduler import run_due as hotspot
from ..planning_workflow_worker import run_once as planning
from ..services.manual_tasks import run_once as manual

LOG = logging.getLogger('application-worker')
JOBS = {'weekly': (60, weekly), 'hotspot': (60, hotspot), 'planning': (10, planning), 'manual': (2, manual)}


def execute(name, handler):
    try:
        result = handler(datetime.now(ZoneInfo('Asia/Shanghai'))) if name in ('weekly','hotspot') else handler()
        failed = isinstance(result,dict) and (result.get('status') in ('failed','error') or result.get('failed',0)
                  or any(row.get('error') or row.get('http_error') or row.get('status')=='failed'
                         for row in result.get('pipelines',[])))
        return {'status': 'failed' if failed else 'ok', 'result': result}
    except Exception as exc:
        LOG.exception('Background job %s failed: %s', name, type(exc).__name__)
        return {'status': 'failed', 'error_type': type(exc).__name__}


def run_once(jobs=None):
    selected = JOBS if jobs is None else jobs
    return {name: execute(name, handler) for name, (_, handler) in selected.items()}


def serve():
    # Independent loops share one process; slow model I/O cannot block other roles.
    with ThreadPoolExecutor(max_workers=len(JOBS), thread_name_prefix='planning-job') as pool:
        pending = {}
        last_reports = {}
        next_due = dict.fromkeys(JOBS, 0.0)
        while True:
            clock = monotonic()
            for name, (interval, handler) in JOBS.items():
                future = pending.get(name)
                if future is not None and future.done():
                    report = future.result()
                    rendered=json.dumps(report, ensure_ascii=True, default=str)
                    if last_reports.get(name)!=rendered:
                        LOG.info('%s %s',name,rendered)
                        last_reports[name]=rendered
                    del pending[name]
                if name not in pending and clock >= next_due[name]:
                    pending[name] = pool.submit(execute, name, handler)
                    next_due[name] = clock + interval
            sleep(1)


def main():
    parser = argparse.ArgumentParser(description='统一运行周调度、热点T-1及策划流程')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.once:
        report = run_once()
        print(json.dumps(report, ensure_ascii=True, default=str))
        return int(any(r['status'] == 'failed' for r in report.values()))
    try:
        serve()
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
