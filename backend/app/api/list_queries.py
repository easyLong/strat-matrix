"""Paged page-query routes; legacy list contracts remain available."""
from fastapi import APIRouter
from .common import invoke
from ..services.list_queries import PageQuery, task_list_query
from ..services.plan_queries import PlanQuery, plan_page
from ..services.result_lists import account_page,period_page,period_context,result_failures
from ..services.result_export import export_page,export_csv,prepare_export
from fastapi.responses import StreamingResponse

router=APIRouter(prefix='/api/query')

@router.post('/manual-tasks')
def manual_tasks(query: PageQuery):
    return invoke(task_list_query, query)

@router.post('/plans')
def planning_records(query: PlanQuery):
    return invoke(plan_page, query)

@router.post('/accounts')
def accounts(query: PageQuery):
    return invoke(account_page,query)

@router.post('/periods')
def periods(query: PageQuery):
    return invoke(period_page,query)

@router.post('/period-context')
def context(query: PlanQuery):
    return invoke(period_context,query.cycle_start,query.cycle_end,query.batch_id,query.filters)

@router.post('/export')
def export(query: PlanQuery):
    query=invoke(prepare_export,query)
    first=invoke(export_page,query)
    return StreamingResponse(export_csv(query,first),media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition':'attachment; filename="planning.csv"'})

@router.post('/failures')
def failures(query: PlanQuery):
    return invoke(result_failures,query)
