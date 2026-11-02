"""One scope/filter model for account, period and batch detail pages."""
from collections import defaultdict
from datetime import date
from typing import Literal

from ..db import connection
from ..models import AccountPlanRecord
from ..bank_bridge.bridge import collect, account_options
from ..bank_bridge.contracts import TopicQuery
from ..bank_bridge.factory import get_source
from ..adapters.mysql.planning_queries import items as read_items
from ..core.planning_items import enrich_plan_item
from .configuration import get_config
from .errors import ApplicationError
from .result_scope import ResultQuery, compile_scope

CONTENT_TYPES = ('三公里好物种草','产品权益种草','三公里活动营销','产品营销','通用活动','金融科普',
                 '热点解读','属地推荐','一句话讨论','财商教育','客群兴趣内容','人设故事')
RELATION = (" FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id "
            "WHERE i.del_flag='N' AND b.del_flag='N' AND ")


PlanQuery = ResultQuery


def plan_page(query: PlanQuery):
    where,params,base,base_params=compile_scope(query)
    filters=query.filters
    with connection() as db, db.cursor() as cursor:
        if filters.get('accountFilters') is not None:
            from .result_lists import account_filter_ids
            selected,_=account_filter_ids(cursor,filters['accountFilters'],get_config().config)
            where.append('i.account_id IN ('+','.join(['%s']*len(selected))+')' if selected else '0=1')
            params.extend(selected)
        cursor.execute('SELECT DISTINCT i.topic_id,i.content_type'+RELATION+base, base_params)
        topic_types = cursor.fetchall()
        missing = sorted({r['topic_id'] for r in topic_types if r['topic_id'] and not r['content_type']})
        lookup = {}
        for offset in range(0,len(missing),500):
            for topic in collect(get_source(cursor),'topics',TopicQuery(topic_ids=missing[offset:offset+500])):
                lookup[topic.topic_id] = topic.content_type
        content_types = sorted({r['content_type'] or lookup.get(r['topic_id'],'') for r in topic_types}-{''})
        wanted = filters.get('contentType')
        if wanted and wanted != 'all':
            legacy = [key for key,value in lookup.items() if value == wanted]
            extra = ' OR (i.content_type=\'\' AND i.topic_id IN ('+','.join(['%s']*len(legacy))+'))' if legacy else ''
            where.append('(i.content_type=%s'+extra+')');params.extend([wanted,*legacy])
        criterion=' AND '.join(where)
        cursor.execute('SELECT COUNT(DISTINCT i.account_id) accounts,COUNT(DISTINCT i.batch_id) batches,'
                       "COUNT(DISTINCT NULLIF(i.topic_id,'')) topics"+RELATION+criterion,params)
        summary = cursor.fetchone()
        cursor.execute('SELECT DISTINCT i.topic_id,i.content_type'+RELATION+criterion,params)
        counts = defaultdict(set)
        for row in cursor.fetchall():
            if row['topic_id']:
                counts[row['content_type'] or lookup.get(row['topic_id'],'')].add(row['topic_id'])
        distribution=[{'name':name,'count':len(counts[name]),'hint':'同一选题在同一内容类型下只计一次'} for name in CONTENT_TYPES]
        others = set().union(*(v for k,v in counts.items() if k and k not in CONTENT_TYPES)) if counts else set()
        if others:distribution.append({'name':'其他','count':len(others),'hint':'历史其他内容类型'})
        if counts['']:distribution.append({'name':'未设置','count':len(counts['']),'hint':'已确定选题但未填写内容类型'})
        key = 'i.id' if query.unit=='records' else 'DATE_SUB(i.publish_date,INTERVAL WEEKDAY(i.publish_date) DAY)' if query.mode=='account' else 'i.account_id'
        cursor.execute('SELECT COUNT(DISTINCT '+key+') total'+RELATION+criterion,params)
        total = cursor.fetchone()['total']
        order = 'MAX(i.publish_date) DESC,group_key DESC' if query.unit=='records' else 'group_key DESC' if query.mode=='account' else 'MIN(i.account_name),group_key'
        cursor.execute('SELECT '+key+' group_key'+RELATION+criterion+' GROUP BY group_key ORDER BY '+order+' LIMIT %s OFFSET %s',
                       [*params,query.page_size,(query.page-1)*query.page_size])
        groups=[r['group_key'] for r in cursor.fetchall()]
        records=[]
        if groups:
            grouped=criterion+' AND '+key+' IN ('+','.join(['%s']*len(groups))+')'
            # Preserve the server's group order, then each group's record order.
            order='FIELD('+key+','+','.join(['%s']*len(groups))+'),i.publish_date DESC,i.id DESC'
            records=read_items(cursor,grouped,[*params,*groups,*groups],order,limit=2147483647)
        accounts=account_options(cursor,get_config().config,limit=1000,account_ids=sorted({r['account_id'] for r in records})) if records else []
        items=[AccountPlanRecord.model_validate(enrich_plan_item(row,row['plan_type'])).model_dump() for row in records]
    return dict(items=items,total=total,page=query.page,page_size=query.page_size,accounts=accounts,
                summary=summary,distribution=distribution,content_types=content_types)
