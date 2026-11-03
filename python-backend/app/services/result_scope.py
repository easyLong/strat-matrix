"""A single normalized result scope shared by details, lists and export."""
from datetime import date
from typing import Literal
from pydantic import Field
from .list_queries import PageQuery, validate_dates
from .errors import ApplicationError

class ResultQuery(PageQuery):
    unit:Literal['groups','records']='groups'
    max_item_id:int|None=Field(default=None,ge=0)
    mode: Literal['account','cycle','batch','all']
    account_id: str | None = None
    batch_id: int | None = None
    account_ids: list[str] | None = Field(default=None,max_length=10000)
    batch_ids: list[int] | None = Field(default=None,max_length=10000)
    cycle_start: date | None = None
    cycle_end: date | None = None

def compile_scope(query):
    where,params=['1=1'],[]
    if query.mode=='account':
        if not query.account_id:raise ApplicationError(422,'请选择账号')
        where.append('i.account_id=%s');params.append(query.account_id)
    elif query.mode=='batch':
        if not query.batch_id or query.batch_id<1:raise ApplicationError(422,'请选择批次')
        where.append('i.batch_id=%s');params.append(query.batch_id)
    elif query.mode=='cycle':
        if not query.cycle_start or not query.cycle_end or query.cycle_start>query.cycle_end:
            raise ApplicationError(422,'请选择有效周期')
        where.extend(['b.cycle_start>=%s','b.cycle_start<=%s']);params.extend([query.cycle_start,query.cycle_end])
    for values,field in ((query.account_ids,'i.account_id'),(query.batch_ids,'i.batch_id')):
        if values is not None:
            where.append(field+' IN ('+','.join(['%s']*len(values))+')' if values else '0=1')
            params.extend(values)
    base=' AND '.join(where);base_params=params.copy()
    filters=query.filters
    if query.max_item_id is not None:
        where.append('i.id<=%s');params.append(query.max_item_id)
    start,end=validate_dates(filters.get('start'),filters.get('end'))
    if start:where.append('i.publish_date>=%s');params.append(start)
    if end:where.append('i.publish_date<=%s');params.append(end)
    if value:=str(filters.get('account') or '').strip().lower():
        where.append('(LOCATE(%s,LOWER(i.account_id))>0 OR LOCATE(%s,LOWER(i.account_name))>0)');params.extend([value,value])
    if filters.get('planType') in ('manual','auto'):
        where.append('b.plan_type=%s');params.append(filters['planType'])
    return where,params,base,base_params
