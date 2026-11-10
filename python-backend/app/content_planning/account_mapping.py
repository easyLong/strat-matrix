"""Resolve reviewed account fields onto published leaf IDs; never infer unknown traits."""
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .account_profile import canonical_json
from .taxonomy import selectable_tags

WEIGHTS = {'CORE': 1.0, 'ADJACENT': 0.75, 'CONDITIONAL': 0.45, 'OFF': 0.0}
SOURCE_FIELDS = ('persona', 'family_identity', 'interests', 'gender', 'expression_style')


class MappingRule(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: int | None = None
    mapping_version: int = Field(ge=1)
    taxonomy_version: int = Field(ge=0)
    source_field: Literal['persona', 'family_identity', 'interests', 'gender', 'expression_style']
    source_value: str = Field(min_length=1, max_length=200)
    target_dimension: Literal['T3', 'T4', 'T5', 'T6', 'STYLE']
    target_level: Literal['L2', 'L3', 'TEXT']
    target_node_id: str = Field(default='', max_length=64)
    target_name: str = Field(default='', max_length=200)
    relation_type: Literal['CORE', 'ADJACENT', 'CONDITIONAL', 'OFF', 'TEXT']
    weight: float | None = Field(default=None, strict=True)
    condition_text: str = Field(default='', max_length=1000)
    target_text: str = Field(default='', max_length=2000)
    status: Literal['draft', 'active', 'disabled'] = 'draft'
    source_reference: str = Field(default='', max_length=200)
    remark: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def validate_rule(self):
        if self.source_value != self.source_value.strip():
            raise ValueError('原始字段值不可包含前后空格')
        if self.target_dimension in ('T6', 'STYLE'):
            if (self.target_level != 'TEXT' or self.relation_type != 'TEXT'
                    or self.target_node_id or self.weight is not None or not self.target_text.strip()
                    or self.condition_text):
                raise ValueError('需求和风格仅保存独立文本，不配置标签或权重')
            if (self.target_dimension == 'T6' and self.source_field != 'persona'
                    or self.target_dimension == 'STYLE' and self.source_field != 'expression_style'):
                raise ValueError('需求能力来自人设，风格映射来自表达风格')
        else:
            if not self.target_node_id or self.target_text or self.relation_type == 'TEXT':
                raise ValueError('结构化映射必须关联已发布节点，不使用自由文本')
            if self.source_field == 'expression_style':
                raise ValueError('表达风格不能映射为T3至T5标签')
            if self.target_level not in ('L2', 'L3') or (
                    self.target_level == 'L2' and (self.target_dimension != 'T3' or self.source_field != 'persona')):
                raise ValueError('只有人设的T3能力允许配置分类继承，其余必须映射末级')
            if self.relation_type == 'CONDITIONAL' and not self.condition_text.strip():
                raise ValueError('条件适配必须说明使用条件')
            if self.relation_type != 'CONDITIONAL' and self.condition_text:
                raise ValueError('使用条件只属于条件适配，其余说明应写入备注')
            expected = WEIGHTS[self.relation_type]
            if self.weight is not None and (isinstance(self.weight, bool) or self.weight != expected):
                raise ValueError('权重必须与适配关系一致')
            self.weight = expected
        return self


def validate_target(rule, taxonomy):
    if rule.target_level == 'TEXT':
        return
    nodes = {n['id']: n for n in taxonomy[rule.target_dimension]}
    node = nodes.get(rule.target_node_id)
    if node is None:
        raise ValueError('映射目标不在绑定词表中')
    level = 'L2' if node.get('node_type') == 'group' else 'L3'
    if level != rule.target_level:
        raise ValueError('映射目标层级与词表不一致')
    enabled = ({n['id'] for n in selectable_tags(taxonomy[rule.target_dimension])}
               if level == 'L3' else {n['id'] for n in nodes.values() if n['enabled']})
    if rule.target_node_id not in enabled:
        raise ValueError('映射目标或其上级已停用')


def field_values(account):
    result = {}
    for field in SOURCE_FIELDS:
        raw = account.get(field)
        values = [] if raw is None else [raw] if isinstance(raw, str) else raw
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError('账号映射字段须为文本或文本数组')
        result[field] = sorted({v.strip() for v in values if v.strip()})
    return result


def _choose(rules):
    # A leaf overrides its own category rule for the same original value.
    groups = {}
    for rule in rules:
        key = rule.source_field, rule.source_value
        previous = groups.get(key)
        if previous is None or (rule.target_level == 'L3' and previous.target_level == 'L2'):
            groups[key] = rule
        elif rule.target_level == previous.target_level and rule != previous:
            raise ValueError('同一映射目标存在重复规则')
    selected = list(groups.values())
    persona = [r for r in selected if r.source_field == 'persona']
    selected = persona or selected
    off = [r for r in selected if r.relation_type == 'OFF']
    if off:
        return off, False
    meanings = {(r.relation_type, r.weight, r.condition_text) for r in selected}
    return selected, len(meanings) > 1


def resolve_mapping(account, taxonomy, rules, *, mapping_version, taxonomy_version, preview=False):
    """Return leaf values + known masks + evidence. CONDITIONAL is never an approval."""
    if type(mapping_version) is not int or mapping_version < 1 or type(taxonomy_version) is not int or taxonomy_version < 0:
        raise ValueError('映射版本或词表版本无效')
    values = field_values(account)
    parsed = [r if isinstance(r, MappingRule) else MappingRule.model_validate(r) for r in rules]
    allowed = ('active', 'draft') if preview else ('active',)
    relevant, ignored = [], []
    for rule in parsed:
        if rule.mapping_version != mapping_version or rule.status not in allowed:
            continue
        if rule.source_value not in values[rule.source_field]:
            continue
        if rule.taxonomy_version != taxonomy_version:
            ignored.append({'rule_id': rule.id, 'reason': 'taxonomy_version_mismatch'})
            continue
        try:
            validate_target(rule, taxonomy)
        except ValueError:
            ignored.append({'rule_id': rule.id, 'reason': 'target_unavailable'})
            continue
        relevant.append(rule)
    features = {}
    for dimension in ('T3', 'T4', 'T5'):
        leaves = sorted(selectable_tags(taxonomy[dimension]), key=lambda n: n['id'])
        resolved = []
        for leaf in leaves:
            candidates = [r for r in relevant if r.target_dimension == dimension and
                          (r.target_node_id == leaf['id'] or
                           r.target_level == 'L2' and r.target_node_id == leaf.get('parent_id'))]
            selected, conflict = _choose(candidates)
            first = selected[0] if selected else None
            known = first is not None and not conflict
            resolved.append({'tag_id': leaf['id'], 'name': leaf['name'], 'parent_id': leaf.get('parent_id'),
                             'value': first.weight if known else None, 'known': known,
                             'relation': first.relation_type if known else 'UNKNOWN',
                             'condition': first.condition_text if known else '',
                             'requires_precision': bool(known and first.relation_type == 'CONDITIONAL'),
                             'reason': 'conflicting_rules' if conflict else 'mapped' if known else 'no_confirmed_rule',
                             'evidence': [{'rule_id': r.id, 'source_field': r.source_field,
                                           'source_value': r.source_value, 'target_level': r.target_level,
                                           'status': r.status} for r in selected]})
        features[dimension] = {'tag_ids': [r['tag_id'] for r in resolved],
                               'values': [r['value'] for r in resolved],
                               'known_mask': [int(r['known']) for r in resolved], 'leaves': resolved}
    texts = {}
    for dimension in ('T6', 'STYLE'):
        candidates = [r for r in relevant if r.target_dimension == dimension]
        descriptions = sorted({r.target_text for r in candidates})
        texts[dimension] = {'known': len(descriptions) == 1,
                            'text': descriptions[0] if len(descriptions) == 1 else None,
                            'rule_ids': [r.id for r in candidates]}
    unmapped = [{'source_field': field, 'source_value': value} for field in SOURCE_FIELDS
                for value in values[field]
                if not any(r.source_field == field and r.source_value == value for r in relevant)]
    # Fingerprint actual rule contents and hierarchy, not merely a version number.
    fingerprint = canonical_json({'mapping_version': mapping_version, 'taxonomy_version': taxonomy_version,
                                 'values': values, 'taxonomy': taxonomy, 'preview': preview,
                                 'rules': sorted([r.model_dump() for r in relevant], key=canonical_json)})
    return {'account_id': account.get('account_id'), 'mapping_version': mapping_version,
            'taxonomy_version': taxonomy_version, 'mapping_hash': sha256(fingerprint.encode()).hexdigest(),
            'preview': preview, 'features': features, 'need_capability': texts['T6'], 'style': texts['STYLE'],
            'raw_expression_style': values['expression_style'],
            'unmapped_values': unmapped, 'ignored_rules': ignored}
