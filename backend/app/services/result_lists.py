"""Server-side account/period list queries over the same formal-result facts."""
from collections import defaultdict
from datetime import timedelta
from ..db import connection
from ..bank_bridge.bridge import account_options
from ..planning_progress import PRODUCTION_STATUS_SQL,PLANNING_FAILURE_SQL
from .configuration import get_config
from .list_queries import PageQuery,validate_dates
from .results import read_batches
from pydantic import BaseModel,ConfigDict,Field,ValidationError,model_validator
from .errors import ApplicationError

class AccountFilters(BaseModel):
    model_config=ConfigDict(extra='forbid')
    keyword:str=''
    umNo:str=''
    organization:str=''
    platform:str=''
    lifecycle:str=''
    accountType:str=''
    followersMin:int|None=Field(default=None,ge=0)
    followersMax:int|None=Field(default=None,ge=0)

    @model_validator(mode='before')
    @classmethod
    def empty_numbers(cls,value):
        if not isinstance(value,dict):raise ValueError('Expected account filter object')
        return {k:(None if k in ('followersMin','followersMax') and v=='' else v) for k,v in value.items()}

    @model_validator(mode='after')
    def valid_range(self):
        if self.followersMin is not None and self.followersMax is not None and self.followersMin>self.followersMax:
            raise ValueError('Invalid follower range')
        return self

WEEK='DATE_SUB(b.cycle_start,INTERVAL WEEKDAY(b.cycle_start) DAY)'
BASE=" FROM godp_planning_batch b WHERE b.del_flag='N' "
ITEMS=(" FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id "
       "LEFT JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag='N' "
       "WHERE i.del_flag='N' AND b.del_flag='N' ")

def account_matches(row,filters):
    for key,field in (('accountType','account_type'),('organization','organization'),('platform','platform'),('lifecycle','lifecycle_stage')):
        if filters.get(key) and row.get(field)!=filters[key]:return False
    if value:=str(filters.get('umNo') or '').strip().lower():
        if value not in str(row.get('um_no') or '').lower():return False
    followers=row.get('followers')
    for key,operator in (('followersMin',lambda x,y:x>=y),('followersMax',lambda x,y:x<=y)):
        value=filters.get(key)
        if value not in (None,'') and (followers is None or not operator(followers,float(value))):return False
    return True

def account_filter_ids(cursor,filters,config):
    try:filters=AccountFilters.model_validate(filters).model_dump()
    except ValidationError:raise ApplicationError(422,'账号筛选条件无效，请检查粉丝量范围') from None
    cursor.execute('SELECT DISTINCT i.account_id'+ITEMS)
    ids=[row['account_id'] for row in cursor.fetchall()]
    profiles=[]
    for offset in range(0,len(ids),500):
        profiles+=account_options(cursor,config,limit=500,account_ids=ids[offset:offset+500])
    by_id={row['account_id']:row for row in profiles}
    wanted=[key for key in ids if account_matches(by_id.get(key,{}),filters)]
    criterion=' AND i.account_id IN ('+','.join(['%s']*len(wanted))+')' if wanted else ' AND 0=1'
    params=list(wanted)
    if value:=str(filters.get('keyword') or '').strip().lower():
        criterion+=' AND (LOCATE(%s,LOWER(i.account_id))>0 OR LOCATE(%s,LOWER(i.account_name))>0)'
        params.extend([value,value])
    cursor.execute('SELECT DISTINCT i.account_id'+ITEMS+criterion,params)
    return [r['account_id'] for r in cursor.fetchall()],profiles

def account_page(query: PageQuery):
    config=get_config().config
    with connection() as db,db.cursor() as cursor:
        wanted,profiles=account_filter_ids(cursor,query.filters,config)
        by_id={row['account_id']:row for row in profiles}
        criterion=' AND i.account_id IN ('+','.join(['%s']*len(wanted))+')' if wanted else ' AND 0=1'
        params=list(wanted)
        cursor.execute('SELECT COUNT(DISTINCT i.account_id) total'+ITEMS+criterion,params)
        total=cursor.fetchone()['total']
        cursor.execute("SELECT i.account_id,MAX(i.account_name) account_name,'' account_owner,"
                       'COUNT(DISTINCT b.cycle_start) cycle_count,COUNT(*) slot_count,'
                       'MAX(b.cycle_start) latest_cycle_start,MAX(b.create_time) latest_cycle_updated_at,'
                       "SUBSTRING_INDEX(GROUP_CONCAT(b.status ORDER BY b.create_time DESC,b.id DESC),',',1) latest_status,"
                       "CAST(SUBSTRING_INDEX(GROUP_CONCAT(b.id ORDER BY b.create_time DESC,b.id DESC),',',1) AS UNSIGNED) latest_batch_id"
                       +ITEMS+criterion+' GROUP BY i.account_id ORDER BY latest_cycle_updated_at DESC,account_name,i.account_id LIMIT %s OFFSET %s',
                       [*params,query.page_size,(query.page-1)*query.page_size])
        rows=cursor.fetchall()
        for row in rows:row['profile']=by_id.get(row['account_id'])
    facets={key:sorted({row.get(field) for row in profiles if row.get(field)}) for key,field in
            (('organizations','organization'),('platforms','platform'),('lifecycles','lifecycle_stage'))}
    return dict(items=rows,total=total,page=query.page,page_size=query.page_size,facets=facets)

def period_criterion(filters):
    start,end=validate_dates(filters.get('startDate'),filters.get('endDate'))
    where,params=[],[]
    if start:where.append('DATE_ADD('+WEEK+',INTERVAL 6 DAY)>=%s');params.append(start)
    if end:where.append(WEEK+'<=%s');params.append(end)
    if value:=str(filters.get('batchQuery') or '').strip().lower():
        where.append('(LOCATE(%s,LOWER(b.batch_code))>0 OR CAST(b.id AS CHAR)=%s)');params.extend([value,value])
    return ''.join(' AND '+part for part in where),params

def period_page(query: PageQuery):
    criterion,params=period_criterion(query.filters)
    with connection() as db,db.cursor() as cursor:
        cursor.execute('SELECT COUNT(DISTINCT '+WEEK+') total'+BASE+criterion,params)
        total=cursor.fetchone()['total']
        cursor.execute('SELECT DISTINCT '+WEEK+' week'+BASE+criterion+' ORDER BY week DESC LIMIT %s OFFSET %s',
                       [*params,query.page_size,(query.page-1)*query.page_size])
        weeks=[row['week'] for row in cursor.fetchall()]
        return _period_rows(cursor,weeks,criterion,params,total,query)

def period_context(start,end,batch_id=None,filters=None):
    filters=dict(filters or {}) if not batch_id else {}
    if start:filters.update(startDate=str(start),endDate=str(end or start))
    criterion,params=period_criterion(filters)
    with connection() as db,db.cursor() as cursor:
        if batch_id:
            cursor.execute("SELECT "+WEEK+" week FROM godp_planning_batch b WHERE b.id=%s AND b.del_flag='N'",(batch_id,))
            row=cursor.fetchone()
            weeks=[row['week']] if row else []
        else:
            cursor.execute('SELECT DISTINCT '+WEEK+' week'+BASE+criterion+' ORDER BY week DESC',params)
            weeks=[r['week'] for r in cursor.fetchall()]
        return _period_rows(cursor,weeks,criterion,params,len(weeks),PageQuery())['items']

def _period_rows(cursor,weeks,criterion,params,total,query):
    if not weeks:return dict(items=[],total=total,page=query.page,page_size=query.page_size)
    cursor.execute('SELECT b.id,'+WEEK+' week'+BASE+criterion+' AND '+WEEK+' IN ('+','.join(['%s']*len(weeks))+')',[*params,*weeks])
    groups=defaultdict(list)
    for row in cursor.fetchall():groups[row['week']].append(row['id'])
    all_ids=[identity for values in groups.values() for identity in values]
    batch_map={};fact_map=defaultdict(list)
    for offset in range(0,len(all_ids),1000):
        chunk=all_ids[offset:offset+1000]
        batch_map.update({row['id']:row for row in read_batches(cursor,batch_ids=chunk,limit=1000)})
        cursor.execute('SELECT i.account_id,i.batch_id,b.plan_type,'
                       f"MIN(CASE WHEN {PRODUCTION_STATUS_SQL} IN ('generated','published') AND NULLIF(i.topic_id,'') IS NOT NULL THEN 1 ELSE 0 END) content_done,"
                       f"MAX(CASE WHEN {PLANNING_FAILURE_SQL} THEN 1 ELSE 0 END) planning_failed"
                       +ITEMS+' AND i.batch_id IN ('+','.join(['%s']*len(chunk))+') GROUP BY i.account_id,i.batch_id,b.plan_type',chunk)
        for row in cursor.fetchall():fact_map[row['batch_id']].append(row)
    output=[]
    for week in weeks:
        ids=groups[week]
        batches=[batch_map[identity] for identity in ids]
        batches.sort(key=lambda row:(row['created_at'],row['id']),reverse=True)
        batches.sort(key=lambda row:row['plan_type']!='auto')
        facts=[fact for identity in ids for fact in fact_map[identity]]
        accounts=defaultdict(list)
        failed_batches={b['id'] for b in batches if b['account_count']>0 and b['failed_count']==b['account_count']}
        for fact in facts:
            fact['planning_failed']=bool(fact['planning_failed'] or fact['batch_id'] in failed_batches)
        for fact in facts:accounts[fact['account_id']].append(fact)
        # Failed selections with no formal items remain explicitly represented by
        # their persisted failure rows; unidentifiable legacy counts are separate.
        failed={key for key,rows in accounts.items() if any(r['planning_failed'] for r in rows)}
        auto={r['account_id'] for r in facts if r['plan_type']=='auto'}
        manual={r['account_id'] for r in facts if r['plan_type']=='manual'}
        output.append(dict(cycleStart=week,cycleEnd=week+timedelta(days=6),batches=batches,
            autoBatches=[b for b in batches if b['plan_type']=='auto'],manualBatches=[b for b in batches if b['plan_type']=='manual'],
            autoAccountCount=len(auto),manualAccountCount=len(manual),accountCount=len(accounts),
            completedCount=len(accounts)-len(failed),failedCount=len(failed),
            contentCompletedAccountCount=sum(all(r['content_done'] for r in rows) for rows in accounts.values()),
            updatedAt=max((b['updated_at'] or b['created_at'] for b in batches),default=None)))
    return dict(items=output,total=total,page=query.page,page_size=query.page_size)

def result_failures(query):
    from .result_scope import compile_scope
    from .periods import failure_account_um,is_execution_error
    from ..adapters.mysql.planning_queries import items as read_items
    where,params,_,_=compile_scope(query)
    with connection() as db,db.cursor() as cursor:
        rows=read_items(cursor,' AND '.join(where),params,'i.account_id,i.batch_id,i.id',limit=2147483647)
        ids=list({row['batch_id'] for row in rows})
        batches=read_batches(cursor,batch_ids=ids,limit=max(len(ids),1))
        failed={b['id'] for b in batches if b['account_count']>0 and b['failed_count']==b['account_count']}
        reasons={}
        if ids:
            cursor.execute("SELECT batch_id,failure_reason FROM godp_manual_task WHERE del_flag='N' AND batch_id IN ("+
                           ','.join(['%s']*len(ids))+') ORDER BY id',ids)
            reasons={r['batch_id']:r['failure_reason'] for r in cursor.fetchall()}
    result={}
    for row in rows:
        if row['batch_id'] in failed or is_execution_error(row['status']) and row.get('production_status')!='failed':
            result.setdefault((row['batch_id'],row['account_id']),dict(batch_code=row['batch_code'],account_id=row['account_id'],
                account_name=row['account_name'],um_no=failure_account_um(row),
                reason=reasons.get(row['batch_id']) or (row['status'] if is_execution_error(row['status']) else '历史任务记录为策划失败')))
    return list(result.values())
