"""Migration-only read bridge. Replace Java's source port with bank SQL onsite.

No preview, business task or formal result is created here.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from .security import require_integration_token
from ..db import connection
from ..services.configuration import get_config
from ..bank_bridge.bridge import account_options, topic_options
from ..services.catalog import attach_topic_labels
from datetime import date

router = APIRouter(prefix='/api/internal/manual-source', dependencies=[Depends(require_integration_token)])


@router.get('/availability')
def availability(publish_date: date):
    from ..manual_availability import planned_manual_accounts, pending_manual_accounts
    with connection() as db, db.cursor() as cursor:
        ids=planned_manual_accounts(cursor,publish_date) | pending_manual_accounts(cursor,publish_date)
    return {'blocked_account_ids':sorted(ids)}


class SourceQuery(BaseModel):
    account_ids: list[str] = Field(default_factory=list, max_length=1000)
    topic_ids: list[str] = Field(default_factory=list, max_length=100)


@router.post('')
def snapshot(query: SourceQuery):
    config = get_config()
    with connection() as db, db.cursor() as cursor:
        accounts = []
        for offset in range(0,len(query.account_ids),500):
            accounts += account_options(cursor,config.config,account_ids=query.account_ids[offset:offset+500])
        topics = topic_options(cursor,topic_ids=list(dict.fromkeys(query.topic_ids))) if query.topic_ids else []
        attach_topic_labels(cursor,topics)
        for topic in topics:
            topic.pop('topic_payload',None)
            topic.pop('_catalog_topic',None)
    import hashlib
    version = hashlib.sha256(config.config.model_dump_json().encode()).hexdigest()
    return {'accounts':accounts,'topics':topics,'algorithm_version':version}


class OperationQuery(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=200)


@router.post('/latest-operations')
def latest_operations(query: OperationQuery):
    """Read old adjustment facts in batches for the transitional Java export."""
    with connection() as db, db.cursor() as cursor:
        cursor.execute('SELECT a.*,a.create_time created_at,a.create_by created_by FROM godp_planning_adjustment a '
                       'JOIN (SELECT item_id,MAX(id) id FROM godp_planning_adjustment '
                       "WHERE del_flag='N' AND item_id IN ("+','.join(['%s']*len(query.item_ids))+') GROUP BY item_id) latest ON latest.id=a.id',query.item_ids)
        return cursor.fetchall()


@router.get('/result-watermark')
def result_watermark():
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT COALESCE(MAX(id),0) max_item_id FROM godp_planning_item WHERE del_flag='N'")
        return cursor.fetchone()
