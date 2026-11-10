"""Planner-owned mapping repository and reusable resolver, independent of bank SQL."""
import json

from ..account_mapping import resolve_mapping
from ..db import connection
from ..taxonomy import normalize_taxonomy
from .errors import ApplicationError


def load_taxonomy(cursor, requested_version=None):
    cursor.execute("SELECT version,config_json FROM godp_strategy_config "
                   "WHERE config_key='tag_taxonomy' AND del_flag='N'")
    current = cursor.fetchone()
    if not current:
        raise ApplicationError(409, '选题标签词表尚未初始化')
    version = current['version'] if requested_version is None else requested_version
    if version != current['version']:
        cursor.execute("SELECT config_json FROM godp_strategy_config_version "
                       "WHERE config_key='tag_taxonomy' AND version=%s AND del_flag='N'", (version,))
        current = cursor.fetchone()
        if not current:
            raise ApplicationError(409, '指定标签词表版本不存在')
    return version, normalize_taxonomy(json.loads(current['config_json']))


def resolve_account_mapping(account, *, mapping_version=1, taxonomy_version=None, preview=False):
    if type(mapping_version) is not int or mapping_version < 1:
        raise ValueError('映射版本必须为正整数')
    with connection() as db, db.cursor() as cursor:
        version, taxonomy = load_taxonomy(cursor, taxonomy_version)
        cursor.execute("SELECT * FROM godp_account_mapping_rule WHERE mapping_version=%s AND del_flag='N' "
                       'ORDER BY id', (mapping_version,))
        rules = cursor.fetchall()
    return resolve_mapping(account, taxonomy, rules, mapping_version=mapping_version,
                           taxonomy_version=version, preview=preview)
