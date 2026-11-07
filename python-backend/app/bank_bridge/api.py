"""Thin HTTP wrappers; embedded hosts call the same source/operations methods."""

from fastapi import APIRouter, Depends, HTTPException
import pymysql

from ..db import connection
from ..integration import require_integration_token
from . import operations
from .contracts import (Account, AccountPlanningQuery, AccountQuery, EffectivePlacement,
                        EffectivePlacementQuery, LabelTestQuery, MarketingContent,
                        MarketingQuery, Page, Topic, TopicIdentity, TopicQuery, UsageQuery,
                        DemandReceipt, MarketingDemand, ProductionQuery, ProductionRecord,
                        PlanningOutput, UsageOutput, LabelOutput, LabelTestOutput)
from .factory import get_source, get_production
from .ports import DataContractError, IntegrationUnavailable
from ..model_capacity import model_api_admission

router = APIRouter(prefix='/api/integrations/bank', tags=['驻场对接契约'],
                   dependencies=[Depends(require_integration_token)])


def invoke(method, *, commit=False):
    try:
        with connection() as db, db.cursor() as cursor:
            result = method(cursor)
            if commit:
                db.commit()
            return result
    except IntegrationUnavailable:
        raise HTTPException(503, '行内对接方法尚未配置，请完成驻场适配') from None
    except DataContractError:
        raise HTTPException(502, '返回数据不符合对接实体，请运行驻场自检核对字段映射') from None
    except (pymysql.MySQLError, ValueError):
        raise HTTPException(503, '对接数据暂不可用，请核对查询实现与数据库连接') from None


@router.post('/if01/accounts/query', response_model=Page[Account])
def query_accounts(query: AccountQuery):
    return invoke(lambda cursor: get_source(cursor).accounts(query))


@router.post('/if02/topics/query', response_model=Page[Topic])
def query_topics(query: TopicQuery):
    return invoke(lambda cursor: get_source(cursor).topics(query))


@router.post('/if03/marketing-contents/query', response_model=Page[MarketingContent])
def query_marketing_contents(query: MarketingQuery):
    return invoke(lambda cursor: get_source(cursor).marketing_contents(query))


@router.post('/if04/effective-marketing/query', response_model=list[EffectivePlacement])
def query_effective_marketing(query: EffectivePlacementQuery):
    return invoke(lambda cursor: get_source(cursor).effective_marketing(query))


@router.post('/if04/production-results/query', response_model=list[ProductionRecord])
def query_production_results(query: ProductionQuery):
    return invoke(lambda cursor: get_production(cursor).production_results(query))


@router.post('/op01/account-planning/query', response_model=PlanningOutput)
def query_account_planning(query: AccountPlanningQuery):
    return invoke(lambda cursor: operations.account_planning(cursor, query))


@router.post('/op02/topic-usage/query', response_model=UsageOutput)
def query_usage(query: UsageQuery):
    return invoke(lambda cursor: operations.topic_usage(cursor, query))


@router.post('/op03/topic-labels/query', response_model=LabelOutput)
def query_labels(query: TopicIdentity):
    return invoke(lambda cursor: operations.topic_labels(cursor, query))


@router.post('/op04/topic-labels/test', response_model=LabelTestOutput,
             dependencies=[Depends(model_api_admission)])
def query_test_labels(query: LabelTestQuery):
    return invoke(lambda cursor: operations.test_labels(cursor, query))
