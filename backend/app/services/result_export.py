"""CSV export over the same normalized scope, without per-row HTTP requests."""
import csv
import io
from ..db import connection
from .plan_queries import plan_page,PlanQuery

HEADERS=['账号ID','账号昵称','投放日期','批次号','策划方式','选题ID','选题标题','选题大纲','选题二级分类','内容状态','最新操作','操作人','操作时间','操作说明']

def prepare_export(query):
    filters=dict(query.filters)
    with connection() as db,db.cursor() as cursor:
        cursor.execute("SELECT COALESCE(MAX(id),0) upper_id FROM godp_planning_item WHERE del_flag='N'")
        upper_id=cursor.fetchone()['upper_id']
    account_ids=query.account_ids
    if filters.get('accountFilters') is not None:
        from .result_lists import account_filter_ids
        from .configuration import get_config
        config=get_config().config
        with connection() as db,db.cursor() as cursor:
            selected,_=account_filter_ids(cursor,filters.pop('accountFilters'),config)
        account_ids=selected if account_ids is None else list(set(account_ids)&set(selected))
    return query.model_copy(update={'page':1,'page_size':200,'unit':'records','filters':filters,'account_ids':account_ids,'max_item_id':upper_id})

def csv_line(values):
    output=io.StringIO()
    clean=[]
    for value in values:
        text='' if value is None else str(value)
        if text.lstrip().startswith(('=','+','-','@','\t','\r')):text="'"+text
        clean.append(text)
    csv.writer(output).writerow(clean)
    return output.getvalue()

def export_page(query):
    result=plan_page(query)
    ids=[item['id'] for item in result['items']]
    operations={}
    if ids:
        with connection() as db,db.cursor() as cursor:
            cursor.execute('SELECT a.*,a.create_time created_at,a.create_by created_by FROM godp_planning_adjustment a '
                           'JOIN (SELECT item_id,MAX(id) id FROM godp_planning_adjustment '
                           "WHERE del_flag='N' AND item_id IN ("+','.join(['%s']*len(ids))+') GROUP BY item_id) latest ON latest.id=a.id',ids)
            operations={row['item_id']:row for row in cursor.fetchall()}
    result['latest_operations']=operations
    return result

def export_csv(query,first):
    yield '\ufeff'+csv_line(HEADERS)
    page=1;result=first
    while True:
        for item in result['items']:
            operation=result['latest_operations'].get(item['id'])
            use=operation is not None
            state='待定题' if not item['topic_id'] else {'planned':'待生产','ready':'生产中','generated':'已完成','published':'已完成','failed':'生产失败'}[item['production_status']]
            yield csv_line([item['account_id'],item['account_name'],item['publish_date'],item['batch_code'],
                '人工策划' if item['plan_type']=='manual' else '自动策划',item['topic_id'],item['topic_title'],
                item['outline'],item['content_type'],state,operation['adjustment_source'] if use else '策划结果生成',
                operation['created_by'] if use else item['plan_type'],operation['created_at'] if use else item['batch_created_at'],
                f"{operation['old_topic_title']} → {operation['new_topic_title']} {operation['reason']}" if use else ''])
        if page*query.page_size>=result['total']:break
        page+=1;result=export_page(query.model_copy(update={'page':page}))
