"""V19 pure scoring: leaf-only mappings, five-route recall and precision gates."""
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo
import re

from .core.matching_common import city_allowed, history_by_account, dot_similarity

IMPLEMENTATION_KEY = 'builtin-v19-quality-v1'
QUALITY_PARAMETERS = {
    'ALG-01': {'similarity':'need_cosine_shifted_0_1','mapping':'leaf_id_known_mask'},
    'ALG-02': {'city_gate':'allow_empty_or_exact','history_gate':'exclude_observed_account_history',
               'off_gate':'any_topic_label','unknown_primary':'hold'},
    'ALG-03': {'recall':'five_route_union_rerank'},
    'ALG-04': {'score_scale':'model_precision_0_100','precision':'pair_joint_judgment'},
    'ALG-09': {'no_candidate':'qualified_only_then_unassigned','system_error':'task_failure'},
}


def topic_labels(annotation):
    return [(annotation['main_t3'], 1.0)] + [(identity, .5) for identity in annotation['related_t3']]


def t3_score(mapping, annotation):
    by_id = {n['tag_id']: n for n in mapping['features']['T3']['leaves']}
    selected = [(by_id.get(identity), coefficient) for identity, coefficient in topic_labels(annotation)]
    if any(n and n['relation'] == 'OFF' for n, _ in selected):
        return None, 'persona_off'
    # Unknown primary directions are held for review, never silently converted to OFF.
    primary = by_id.get(annotation['main_t3'])
    if not primary or not primary['known']:
        return None, 'unmapped_primary_topic'
    known = [(n['value'], c) for n, c in selected if n and n['known']]
    return sum(v*c for v,c in known) / sum(c for _,c in known), None


def masked_score(mapping, annotation, dimension):
    by_id = {n['tag_id']: n for n in mapping['features'][dimension]['leaves']}
    known = [by_id[t]['value'] for t in annotation[dimension.lower()] if t in by_id and by_id[t]['known']]
    return sum(known) / len(known) if known else .5


def valid_on(topic, publish_date):
    target = date.fromisoformat(str(publish_date)[:10])
    start, end = topic.get('valid_from'), topic.get('valid_to')
    def local_day(value):
        return datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Shanghai')).date()
    return (not start or local_day(start) <= target) and (not end or target <= local_day(end))


def recall(account, topics, annotations, mapping, need_vector, topic_need_vectors, inputs, options):
    dates = [p['publish_date'] for p in inputs['positions'] if p['account_id'] == account['account_id']]
    history = history_by_account(inputs['supplemental']).get(account['account_id'], set())
    observed = Counter(annotations[t]['main_t3'] for t in history if t in annotations)
    eligible, rejected = [], []
    for topic in topics:
        identity = topic['topic_id']
        cause = None
        if not city_allowed(account, topic): cause = 'region_not_allowed'
        elif topic['source_payload'].get('is_marketing') and not account['profile']['account'].get('marketing_eligible'): cause = 'marketing_not_allowed'
        elif identity in history: cause = 'observed_history'
        elif not any(valid_on(topic, d) for d in dates): cause = 'outside_publish_dates'
        score, mapped_cause = t3_score(mapping, annotations[identity])
        cause = cause or mapped_cause
        if cause:
            rejected.append({'topic_id': identity, 'reason': cause})
            continue
        cosine = dot_similarity(need_vector, topic_need_vectors[identity])
        signals = {'t3': score, 't4': masked_score(mapping, annotations[identity], 'T4'),
                   't5': masked_score(mapping, annotations[identity], 'T5'), 't6': (1 + cosine)/2}
        signals['explore'] = 1/(1 + observed[annotations[identity]['main_t3']])
        eligible.append({'topic_id': identity, 'signals': signals,
                         'recall_score': sum(signals[k]*w for k,w in options.recall_weights.items())})
    channels, union = {}, {}
    for channel, quota in options.quotas.items():
        chosen = sorted(eligible, key=lambda r: (-r['signals'][channel], r['topic_id']))[:quota]
        channels[channel] = [r['topic_id'] for r in chosen]
        for row in chosen:
            union.setdefault(row['topic_id'], {**row, 'routes': []})['routes'].append(channel)
    ranked = sorted(union.values(), key=lambda r: (-r['recall_score'], r['topic_id']))[:options.recall_limit]
    return {'channels': channels, 'quota_total': sum(options.quotas.values()),
            'retrieved_before_dedup': sum(map(len, channels.values())), 'unique_candidates': len(union),
            'ranked': ranked, 'rejected': rejected}


def _title(value):
    return ''.join(re.findall(r'[\w\u4e00-\u9fff]', value.lower()))


def history_penalty(title, history_titles):
    value = _title(title)
    if not value: return 0.0, False
    scores = []
    for other in history_titles:
        other = _title(other)
        if value == other: return 1.0, True
        left = {value[i:i+2] for i in range(len(value)-1)}
        right = {other[i:i+2] for i in range(len(other)-1)}
        if left and right: scores.append(len(left & right) / len(left | right))
    return max(scores, default=0.0), False


def precision_score(judgment, options, *, conditional=False, adjacent=False, repeat_penalty=0, exact_duplicate=False):
    reason = None
    if exact_duplicate: reason = 'exact_duplicate'
    elif judgment['decision'] == 'DROP': reason = 'model_drop'
    elif conditional and judgment['condition_met'] is not True: reason = 'condition_not_met'
    elif judgment['j_topic'] < options.minimum_topic_fit: reason = 'topic_fit_below_threshold'
    elif adjacent and options.minimum_adjacent_topic_fit is not None and judgment['j_topic'] < options.minimum_adjacent_topic_fit:
        reason = 'adjacent_topic_fit_below_threshold'
    base = sum(judgment[k]*w for k,w in options.precision_weights.items())
    final = max(0.0, base - options.repeat_weight*repeat_penalty)
    if not reason and final < options.minimum_precision: reason = 'precision_below_threshold'
    return {'base_precision': base, 'final_precision': final, 'repeat_penalty': repeat_penalty,
            'accepted': reason is None, 'rejection_reason': reason}
