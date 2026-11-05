"""Immutable model cache and lease-guarded progress for existing matching tasks."""
from time import monotonic
import json

from fastapi import HTTPException

from .account_profile import canonical_json
from .db import connection
from .matching_quality_snapshot import content_hash


class QualityPending(Exception):
    """A bounded worker turn finished; the existing durable task must be requeued."""


class QualityRuntime:
    def __init__(self, context, renew, *, max_calls=4, max_seconds=120):
        self.context, self.renew = context, renew
        self.max_calls, self.max_seconds, self.started = max_calls, max_seconds, monotonic()
        self.stats = {'model_calls': 0, 'cache_hits': 0, 'cache_writes': 0}
        self._memory = {}

    def prompt_version(self,kind):
        return self.context.get('prompt_contracts',{}).get(kind,self.context['options']['prompt_version'])

    def key(self, kind, payload):
        model = self.context['embedding_model' if kind == 'need_vector' else 'chat_model']
        meta = {'kind': kind, 'model': model, 'prompt': self.prompt_version(kind),
                'taxonomy_version': self.context['taxonomy_version'],
                'mapping_version': self.context['options']['mapping_version'], 'payload': payload}
        return content_hash(meta), model

    @staticmethod
    def _decode(row):
        if row is None:return None
        value=json.loads(row['result_json'])
        if content_hash(value)!=row['result_hash']:
            raise ValueError('模型缓存完整性校验失败')
        return value

    def prefetch(self,kind,payloads):
        keys=list(dict.fromkeys(self.key(kind,p)[0] for p in payloads))
        keys=[k for k in keys if k not in self._memory]
        for offset in range(0,len(keys),100):
            group=keys[offset:offset+100]
            with connection() as db,db.cursor() as cursor:
                cursor.execute("SELECT cache_key,result_json,result_hash FROM godp_matching_ai_cache WHERE del_flag='N' AND cache_key IN ("
                               +','.join(['%s']*len(group))+')',group)
                rows=cursor.fetchall()
            pending={k:None for k in group}
            for row in rows:
                if row['cache_key'] not in pending:raise ValueError('缓存返回范围不一致')
                self._decode(row)
                pending[row['cache_key']]=row
            self._memory.update(pending)

    def find(self, kind, payload, *, count_hit=True,refresh=False):
        key, _ = self.key(kind, payload)
        if refresh or key not in self._memory:
            with connection() as db, db.cursor() as cursor:
                cursor.execute("SELECT result_json,result_hash FROM godp_matching_ai_cache WHERE del_flag='N' AND cache_key=%s", (key,))
                self._memory[key]=cursor.fetchone()
        value=self._decode(self._memory[key])
        if value is None:return None
        self.stats['cache_hits'] += int(count_hit)
        return value

    def save(self, kind, payload, value):
        key, model = self.key(kind, payload)
        with connection() as db, db.cursor() as cursor:
            cursor.execute('INSERT INTO godp_matching_ai_cache '
                           '(cache_key,task_kind,model_name,prompt_version,taxonomy_version,mapping_version,result_json,result_hash) '
                           'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE cache_key=cache_key',
                           (key, kind, model, self.prompt_version(kind), self.context['taxonomy_version'],
                            self.context['options']['mapping_version'], canonical_json(value), content_hash(value)))
            self.stats['cache_writes'] += int(cursor.rowcount == 1)
            db.commit()
        # If another task published the same key, consume the immutable winner.
        return self.find(kind, payload, count_hit=False,refresh=True)

    def call(self, compute):
        if self.stats['model_calls'] >= self.max_calls or monotonic() - self.started >= self.max_seconds:
            raise QualityPending()
        self.renew()
        self.stats['model_calls'] += 1
        value = compute()
        self.renew()
        return value

    def cached(self, kind, payload, compute, validate=lambda value: value):
        value = self.find(kind, payload)
        if value is None:
            value = validate(self.call(compute))
            value = self.save(kind, payload, value)
        return validate(value)


def save_quality_report(job, report, status, phase):
    encoded = canonical_json(report)
    with connection() as db, db.cursor() as cursor:
        cursor.execute('SELECT status,lease_id,lease_expires_at>UTC_TIMESTAMP(6) live '
                       "FROM godp_matching_task WHERE id=%s AND del_flag='N' FOR UPDATE", (job['task_id'],))
        task = cursor.fetchone()
        if not task or task['status'] != 'processing' or task['lease_id'] != job['lease_id'] or not task['live']:
            raise HTTPException(409, '适配质量执行租约已变化')
        cursor.execute('INSERT INTO godp_matching_quality_run (task_id,lease_id,status,phase,report_json,report_hash) '
                       'VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE lease_id=VALUES(lease_id),'
                       'status=VALUES(status),phase=VALUES(phase),report_json=VALUES(report_json),report_hash=VALUES(report_hash)',
                       (job['task_id'], job['lease_id'], status, phase, encoded, content_hash(report)))
        db.commit()


def read_quality_report(task_id):
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT status,phase,report_json,report_hash FROM godp_matching_quality_run WHERE del_flag='N' AND task_id=%s", (task_id,))
        row = cursor.fetchone()
    if not row: return None
    report = json.loads(row['report_json'])
    if content_hash(report) != row['report_hash']:
        raise ValueError('适配质量报告完整性校验失败')
    return {'status': row['status'], 'phase': row['phase'], 'report': report}
