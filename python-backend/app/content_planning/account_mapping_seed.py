"""Reviewable V19 examples; resolve names to real IDs without creating taxonomy nodes."""
from .account_mapping import MappingRule
from .taxonomy import selectable_tags

REFERENCE = 'V19账号信息与映射规则版'

# persona, level, node names, relationship, condition
PERSONA_RULES = [
    ('福利专家', 'L2', ['福利与权益', '本地生活'], 'CORE', ''),
    ('福利专家', 'L2', ['兴趣与生活方式'], 'ADJACENT', ''),
    ('福利专家', 'L3', ['信用卡', '用卡权益'], 'CONDITIONAL', '内容核心须围绕优惠或权益，不适用于专业用卡知识。'),
    ('福利专家', 'L3', ['基金'], 'OFF', ''),
    ('车圈达人', 'L2', ['汽车与车生活'], 'CORE', ''),
    ('车圈达人', 'L2', ['本地生活'], 'ADJACENT', ''),
    ('车圈达人', 'L3', ['旅游'], 'ADJACENT', ''),
    ('车圈达人', 'L3', ['信贷融资', '信用卡'], 'CONDITIONAL', '须与车贷、汽车消费或车主权益相关。'),
    ('车圈达人', 'L2', ['福利与权益'], 'CONDITIONAL', '须与加油、停车或其他车主权益相关。'),
    ('信用卡专家', 'L3', ['信用卡'], 'CORE', ''),
    ('信用卡专家', 'L2', ['福利与权益'], 'ADJACENT', ''),
    ('信用卡专家', 'L3', ['账户与支付'], 'ADJACENT', ''),
    ('信用卡专家', 'L2', ['本地生活', '兴趣与生活方式', '汽车与车生活'], 'CONDITIONAL',
     '须自然关联支付、用卡、积分、活动或权益。'),
    ('理财专家', 'L3', ['存款', '银行理财', '基金', '保险保障', '贵金属', '外汇', '资产配置', '养老金融', '市场行情', '宏观财经'], 'CORE', ''),
    ('理财专家', 'L3', ['账户与支付'], 'ADJACENT', ''),
    ('理财专家', 'L2', ['家庭与人生', '职场与经营'], 'CONDITIONAL', '须回到预算、储蓄、资产、现金流或财富规划。'),
    ('信贷专家', 'L3', ['信贷融资', '征信'], 'CORE', ''),
    ('信贷专家', 'L3', ['小微经营'], 'ADJACENT', ''),
    ('信贷专家', 'L3', ['购车选车'], 'CONDITIONAL', '须涉及车贷、利率、还款或购车资金安排。'),
    ('信贷专家', 'L3', ['家庭规划'], 'CONDITIONAL', '须涉及贷款、还款、现金流或资金周转。'),
    ('信贷专家', 'L2', ['职场与经营'], 'CONDITIONAL', '须涉及贷款、融资、利率、还款或资金周转。'),
]

NEEDS = {
    '福利专家': '帮助用户发现优惠、权益、本地活动和实用生活信息，降低生活决策成本。',
    '车圈达人': '帮助用户解决选车、用车、养车、用车成本和自驾出行相关问题。',
    '信用卡专家': '帮助用户理解信用卡规则，解决用卡、支付、积分、账单、年费与权益使用问题。',
    '理财专家': '帮助用户理解储蓄、投资、行情与风险，解决资产配置和家庭财富规划相关问题。',
    '信贷专家': '帮助用户理解贷款、融资、征信、利率与还款，解决现金流和资金周转相关问题。',
}

FIELD_RULES = [
    ('family_identity', '有娃', 'T4', '有娃家庭', 'CORE'),
    ('family_identity', '有娃', 'T5', '亲子出行', 'ADJACENT'),
    ('interests', '运动', 'T4', '运动人群', 'CORE'),
    ('interests', '旅游', 'T4', '旅行人群', 'CORE'),
    ('gender', '男', 'T4', '男性', 'CORE'),
    ('gender', '男性', 'T4', '男性', 'CORE'),
    ('gender', '女', 'T4', '女性', 'CORE'),
    ('gender', '女性', 'T4', '女性', 'CORE'),
]


def build_seed_rules(taxonomy, taxonomy_version, mapping_version=1):
    rules, unresolved = [], []
    common = dict(mapping_version=mapping_version, taxonomy_version=taxonomy_version,
                  status='draft', source_reference=REFERENCE,
                  remark='V19示例初始化，待业务确认；未配置项保持UNKNOWN。')

    def add(field, value, dimension, level, name, relation, condition=''):
        items = [n for n in taxonomy[dimension] if n['name'] == name
                 and ('L2' if n.get('node_type') == 'group' else 'L3') == level]
        enabled = {n['id'] for n in (selectable_tags(taxonomy[dimension]) if level == 'L3'
                                     else [n for n in taxonomy[dimension] if n['enabled']])}
        items = [n for n in items if n['id'] in enabled]
        if len(items) != 1:
            unresolved.append({'source_value': value, 'dimension': dimension, 'target_name': name,
                               'reason': 'target_missing_disabled_or_ambiguous'})
            return
        rules.append(MappingRule(**common, source_field=field, source_value=value,
                     target_dimension=dimension, target_level=level, target_node_id=items[0]['id'],
                     target_name=name, relation_type=relation, condition_text=condition))

    for persona, level, names, relation, condition in PERSONA_RULES:
        for name in names:
            add('persona', persona, 'T3', level, name, relation, condition)
    for persona, text in NEEDS.items():
        rules.append(MappingRule(**common, source_field='persona', source_value=persona,
                     target_dimension='T6', target_level='TEXT', relation_type='TEXT', target_text=text))
    for field, value, dimension, name, relation in FIELD_RULES:
        before = len(rules)
        add(field, value, dimension, 'L3', name, relation)
        if len(rules) > before:
            rules[-1].remark = 'V19字段映射示例；性别别名及场景权重为初始化建议，待确认后启用。'
    rules.append(MappingRule(**common, source_field='expression_style', source_value='干货J人',
                 target_dimension='STYLE', target_level='TEXT', relation_type='TEXT',
                 target_text='以清单、步骤、攻略表达，信息密度高。'))
    return rules, unresolved
