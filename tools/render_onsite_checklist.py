"""Render the reviewed CSV checklist into Markdown and a filterable workbook; no service access.

Run from repository root: python tools/render_onsite_checklist.py
Requires openpyxl in the documentation author's environment, not any runtime service.
"""
from __future__ import annotations

from collections import Counter
import csv
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
STEM='三工程驻场功能流程适配清单_V1.0_2026-11-03'
CSV=ROOT/'docs'/f'{STEM}.csv'

SOURCE_CAPABILITIES=[
 ['B01','accounts','账号ID列表、分页、更新时间范围','账号/人设/组织/近三个月互动','Java SourceFacts→行内SQL/Service；Python经Java HTTP读','资格/权限先于count；UM批量解析另需补能力'],
 ['B02','topics','ID列表、分页、更新时间、来源、类型、可用及有效时点','普通/热点候选和营销/非营销类型选题','Java SourceFacts→行内选题库','来源≠类型；不是已生成营销内容'],
 ['B03','marketing-contents','账号ID、分页','审核通过且可引用的账号营销内容','Java读取内容系统','审核时间/内容ID升序；当前契约没有更新时间筛选'],
 ['B04','effective-marketing','账号ID、投放日期','当日真实有效营销投放','Java读取发布/内容事实','有效投放≠已生成；已有则直接引用'],
 ['B05','production-status','slot_ids（1～500）','槽位/版本/内容ID/生产任务ID/状态/更新时间','Java查询内容状态→更新策划业务表','只能采纳匹配版本；不是Python领取/回传接口'],
 ['B06','marketing-status','task_codes（1～500）','营销生产/失败/分配进度','Java查询内容任务事实','生产完成≠过审可排期'],
 ['B07','marketing-allocations','task_code','已过审且分配到账号的内容','Java查询审核分配事实→Java编排投放日期','需task_code→内容ID→账号ID完整关联'],
]
JOBS=[
 ['CONFIGURATION','恢复未确认配置发布','按宿主轻量推进频率','配置命令/算法回执→生效配置','无游标；错误需重试','C02'],
 ['MANUAL','普通人工任务委派/查询/正式落库','按宿主频率持续推进','Java人工任务↔Python人工计算','needs_next_tick提示后续继续，不是立即无间隔循环','D04'],
 ['AUTOMATIC','推进未完自动任务并检查周策划到期','周期性检查，具体业务日时仍由配置判断','Java自动任务↔Python Pipeline/提案','retry_required要记录待重试，不能只跑一次周cron','F01;F02'],
 ['HOTSPOT','每日仅检查明天热点空槽','宿主每日触发，可控重试','明日空槽+热点→正式待生产明细','limit/afterId分页，同次固定now；次日重置游标','G04'],
 ['MARKETING','自动营销有效投放/过审内容引用','按宿主频率扫描','自动明细+内容事实→内容ID引用','has_more/next_after_id继续；失败不推进','G03'],
 ['MARKETING_PLACEMENT','人工营销过审分配后安排投放日','按宿主频率扫描','任务+过审内容+账号→日期/正式明细','按limit选未完成任务；不是所有角色均用同一游标语义','G02'],
 ['CONTENT_STATUS','普通/热点生产状态对账','按内容状态时效要求扫描','内容事实→正式明细状态','当前服务limit≤200；终态和版本保护','G05;B05'],
 ['MARKETING_STATUS','营销任务内容数量/状态对账','按内容状态时效要求扫描','任务进度→营销任务表','has_more/next_after_id；审核分配仍另查','G05;B06'],
 ['ALGORITHM','唤醒planning/manual_compute计算角色','在有任务及恢复需要时由宿主触发','持久化算法任务→受控后台执行','202/accepted仅受理；不另起自主调度或独立Worker','E05'],
]
JAVA_TABLES=[
 ('godp_manual_preview','人工选择冻结预览','D04'),('godp_manual_task','普通人工业务任务','D04'),
 ('godp_manual_marketing_task','营销需求/生成数量/进度/后续批次','D05;G02'),('godp_manual_reservation','同日账号占用与失败释放','D04'),
 ('godp_planning_batch','正式批次快照','F02;H02'),('godp_planning_item','正式槽位/选题/账号快照/版本/内容状态','F02;G01;H03'),
 ('godp_planning_adjustment','操作/换题记录','H04;H05'),('godp_planning_task_archive','已确认旧任务只读归档','D06'),
 ('godp_business_planning_config','四项业务规则权威值','C02'),('godp_business_planning_config_version','业务规则版本','C03'),
 ('godp_planning_config_release','综合发布命令/历史/两侧确认','C02'),('godp_auto_planning_task','周自动业务任务/提案提交确认','F01;F02'),
 ('godp_planning_resource_claim','热点日占用/营销内容引用防重复','G03;G04'),('godp_planning_failure','批次失败账号与原因','F03'),
]
PYTHON_TABLES=[
 ('godp_system_config','系统及模型/运行配置','A08;E01'),('godp_strategy_config','算法规则/词表权威配置','C04;C05'),
 ('godp_strategy_config_version','算法配置历史','C03;C05'),('godp_algorithm_config_command','Java配置发布幂等回执','C02'),
 ('godp_account_mapping_rule','账号画像正式映射规则','E04'),('godp_topic_label_job','选题打标任务/租约','E02'),
 ('godp_topic_tag','选题标签扩展','E02;I03'),('godp_topic_tag_history','标签历史','E02;I03'),('godp_t6_tag','T6算法标签资产','C05;E02'),
 ('godp_topic_profile','选题画像与向量','E02'),('godp_ai_preparation','任务范围的输入准备','E03;E05'),
 ('godp_ai_preparation_account','当前准备任务账号画像/向量/状态','E03'),('godp_ai_preparation_topic','当前准备任务选题快照/准备','E02'),
 ('godp_ai_preparation_progress','准备进度','E05'),('godp_matching_policy','匹配策略及批准状态','E04'),
 ('godp_matching_task','V19匹配任务','E04'),('godp_matching_input_snapshot','冻结匹配输入','E05'),('godp_matching_attempt','匹配执行尝试/租约','E05'),
 ('godp_matching_ai_cache','模型精判/映射等缓存','E04'),('godp_matching_quality_run','V19质量运行及报告','E04'),
 ('godp_manual_compute','普通人工分配计算任务（不是V19）','D04'),('godp_planning_pipeline_run','自动算法流程','E05'),
 ('godp_planning_stage_run','七阶段进度','E05'),('godp_algorithm_proposal','不可变算法提案及Java确认引用','F02'),
]
DATABASES=(
 [['Java业务库',name,purpose,'Java业务服务','策划侧业务数据，不复制行内基础表',ids] for name,purpose,ids in JAVA_TABLES]
 +[['Python算法库',name,purpose,'Python算法服务','核心表族参考，非已核准最小DDL全集',ids] for name,purpose,ids in PYTHON_TABLES]
 +[['行内原始库/服务','账号/选题/营销内容/互动/生产/审核/投放原始资产','原始事实','行内业务/内容系统','真实表名不在本清单中猜测；Python仅经Java查询','B01;B02;B03;B04;B05;B06;B07']]
)
BLOCKERS=[
 ['Q01','模型出口与固定方舟地址','高','E01','行内是否允许方舟、使用何网关/协议/证书/代理/模型及数据范围？','模型/网络/安全团队','未确认不能保证打标/向量/V19真实运行；需模型客户端适配。'],
 ['Q02','真实账号/选题来源和权限','高','B01;B02','哪些表/Service、稳定ID、资格/上下架、组织权限和更新时间可用？','行内账号/选题开发','需真实SQL/Service及权限实施，不是空Bean即可上线。'],
 ['Q03','前1000候选与UM导入','高','D01;D02;D03','全量规模多大？可否提供服务端筛选分页和UM批量解析？','策划前后端/行内资料开发','属于新增开发缺口，不能把候选未加载当账号/选题不存在。'],
 ['Q04','真实内容消费与关联','高','G01;G02;B05;B07','内容方如何读普通/热点明细与营销需求，是否保留slot_id/version/task_code？','内容生成/审核/分配团队','真实扫描器不在本项目中伪造；缺关联无法状态对账。'],
 ['Q05','正式OP数据源','高','I01;I02;I03','最终Java入口和字段契约是什么？旧Python结果/计数何时退出？','行内接口调用方/Java/Python','页面迁移已完成不代表所有OP迁移已完成。'],
 ['Q06','数据库最小发布范围','高','A07','Python历史业务表/工作流依赖哪些必须保留、哪些不发布？业务库实际数据库版本是什么？','DBA/Java/Python','不能整包初始化旧schema，也不能先删兼容表；需依赖核查。'],
 ['Q07','V19正式策略与映射','高','E04','哪些规则/词表/模型空间正式批准，质量阈值及历史内容→选题关联如何提供？','运营/算法/行内数据开发','不复制行外测试批准ID；草稿规则不冒充正式版本。'],
 ['Q08','营销日期和有效投放','中','B04;G02;G03','有效投放如何定义？生成/过审/分配如何区分？56天排期范围是否接受？','运营/内容/Java','当前实现是参考，未确认的规则列为待澄清，不擅自改逻辑。'],
 ['Q09','宿主身份、机构范围与响应','高','A03;A04;H01','Actor/会话取值、机构范围、API错误格式、Advice优先级和下载如何对接？','宿主Java/前端/权限开发','UNSPECIFIED不等于ALL；count/list/详情/导出均需权限。'],
 ['Q10','调度推进而非只点火','高','F01;J01','九类任务由几个Job推进，频率/游标/失败/重试/告警如何接？','宿主调度/运维/Java','只唤醒Python或只跑一次周任务，会漏Java正式提交/状态/配置恢复。'],
 ['Q11','历史、恢复及失败重建','中','C03;F03;H01','哪些行外历史要迁？标签独立历史如何恢复？同周期失败如何重建？','运营/项目负责人/Java','行外演示数据不自动进入行内；历史规则需单独确认。'],
 ['Q12','验收样本与真实闭环','高','C02;J04','是否有授权模型、账号/选题、内容扫描/审核配合和受控写入范围？','各模块责任人/测试','离线固定回放或普通闭环不能代替真实营销/热点、权限、模型质量验收。'],
]
PHASES=[
 ['0','进场前补齐与冻结','确认52项分工，准备1000候选/UM批量能力、模型网关适配、正式OP及最小DDL依赖核查；准备离线制品。','A01;A07;D01;D02;D03;E01;I01;I02;I03;J02','拿到宿主样例与依赖，未决项有责任人，固定回归可离线执行。'],
 ['1','工程/网络/数据基础','三个工程编译；两库发布；可信身份和双向HTTP；7能力只读验收。','A01;A02;A03;A04;A05;A06;A07;A08;B01;B02;B03;B04;B05;B06;B07','无模拟回落；只读样本字段、权限及分页准确，未提供样本不能记通过。'],
 ['2','普通人工闭环','配置初始化→账号/选题选择→提交→受控计算→Java正式明细→查看/导出。','C01;C02;D01;D02;D03;D04;D06;H01;H02;H03','幂等、重启恢复、真实创建人、页面及导出一致。'],
 ['3','普通自动真实模型闭环','批准词表/映射/策略→准备/打标/向量→V19→提案→Java提交确认→真实内容→计次。','C04;C05;E01;E02;E03;E04;E05;F01;F02;G01;G05;I02','先1账号/周期，再3～5账号逐项解释；页面配置确实进入冻结输入。'],
 ['4','营销、热点、失败和换题','人工营销消费/审核/分配/日期，自动营销有效投放引用，明日热点/兜底，换题版本及失败处理。','D05;B03;B04;B06;B07;F03;G02;G03;G04;H04;H05','真实内容团队参与；生成/过审/分配状态准确，旧版本不覆盖新题。'],
 ['5','全量权限/容量/发布验收','三页面嵌入、正式OP、旧路径退出、大量分页/导出、多实例与恢复演练。','A09;H01;H02;H03;H05;I01;I02;I03;J01;J02;J03;J04','无越权、无旧库写入、无假绿调度；模型/状态/导出/日志可核对。'],
]


def load_rows():
    with CSV.open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream))
    ids={row['编号'] for row in rows}
    if len(ids)!=len(rows) or len(rows)!=52:
        raise ValueError('Checklist requires 52 unique reviewed rows')
    for row in rows:
        if not all(row.values()): raise ValueError('Empty checklist field: '+row['编号'])
        for source in row['代码定位'].split(';'):
            if not (ROOT/source).exists(): raise ValueError('Missing code location: '+source)
        for dependency in row['前置项'].split(';'):
            if dependency!='—' and dependency not in ids: raise ValueError('Unknown dependency: '+dependency)
    by_id={row['编号']:row for row in rows}
    done=set()
    def visit(identity,stack):
        if identity in stack: raise ValueError('Cyclic dependency: '+' -> '.join(stack+[identity]))
        if identity in done:return
        for dependency in by_id[identity]['前置项'].split(';'):
            if dependency!='—':visit(dependency,stack+[identity])
        done.add(identity)
    for identity in ids:visit(identity,[])
    source='\n'.join(path.read_text(encoding='utf-8') for path in (ROOT/'java-backend/godp-planning-services/src/main/resources/db').glob('*.sql'))
    tables=set(re.findall(r'CREATE TABLE IF NOT EXISTS (godp_\w+)',source))
    if tables!={name for name,_,_ in JAVA_TABLES}:raise ValueError('Java table inventory differs from DDL')
    py_schema='\n'.join(path.read_text(encoding='utf-8') for path in (ROOT/'python-backend').glob('*.sql'))
    for name,_,_ in PYTHON_TABLES:
        if not re.search(r'CREATE TABLE IF NOT EXISTS '+name+r'\b',py_schema):raise ValueError('Unknown Python core table: '+name)
    return rows


def table(headers,rows):
    def cell(value):return str(value).replace('|','\\|').replace('\n','<br>')
    return '\n'.join(['| '+' | '.join(map(cell,headers))+' |','| '+' | '.join(['---']*len(headers))+' |']
                     +['| '+' | '.join(map(cell,row))+' |' for row in rows])+'\n'


def render_md(rows):
    effort=Counter(row['工作量级别'] for row in rows)
    sections=[
      '# 三工程驻场功能流程适配清单 V1.0\n',
      '日期：2026-11-03（北京时间）。基于当前工作区代码核查；包含尚未提交的近期抽象改造，不等于已部署版本或已完成行内验收。共52项功能/流程适配，供驻场分工、需求澄清与验收跟踪。\n',
      f'配套：[可筛选Excel]({STEM}.xlsx) · [逐项CSV源数据]({STEM}.csv)。Excel的前端/Java/Python页是同一总表按工程筛选，同一跨工程项会重复出现，不能累加计算工作量。\n',
      '## 1. 当前整合边界\n',
      '本项目作为行内子模块分别迁入三个已有工程：Vue只访问宿主Java；Java负责业务配置、任务、正式结果、权限与内容状态投影；Python负责算法参数、词表、打标、画像、向量、V19及持久化计算。原始账号/选题/内容由行内维护，Java通过预留方法查询；Python不直连行内业务库。\n',
      '```text\n宿主前端三个页面 → 宿主Java业务服务 → Java策划业务库\n                         │ 内网HTTP委派/查结果\n                         ▼\n                  Python算法服务 → Python算法库\n                         │ 内网HTTP读取资料/正式使用次数\n                         └──────────→ 宿主Java资料方法 → 行内原始库/现有Service\n\n内容侧经授权读取Java待生产明细/营销需求 → 自行生成/审核/分配 → 内容侧事实\n宿主调度 → Java任务推进 → 查询上述内容事实 → 更新Java内容状态/进度\n```\n',
      '内容侧实际扫描器和Agent执行不由本项目伪造；默认按已讨论的授权读策划表/视图衔接，状态仍由策划侧查询。无法读表时再共同确认宿主查询能力，不预设增加Python领取/回调系统。两侧自有库物理隔离；行内原始资料可以位于宿主既有数据源或Service，并非要求复制到策划业务库。\n',
      'Java正式结果中的账号/选题快照，以及Python用于恢复和复现的冻结输入，是必要计算/历史资产，不是另建一套行内账号或选题主数据同步。进场需核对inside、Java资料HTTP、AUTO_SCHEDULE_OWNER=java、内容模拟禁用以及新自动流程commit_owner=java，避免遗留路径成为第二个正式业务写入方。\n',
      '## 2. 核查结论与工作量口径\n',
      '已实现可复用：三页面、Java主要业务服务/MyBatis、两侧配置发布与正式结果确认、SourceFacts骨架/映射、请求上下文、响应适配、统一分页、Python人工分配及V19、固定回归与只读自检。尚未完成真实行内身份、权限SQL、原始资料查询、模型出口、内容生产/审核/分配及宿主调度验收。\n',
      f'工作量级别分布：高{effort["高"]}项，中{effort["中"]}项。高表示跨团队/真实资料/权限或需补开发；中表示已有稳定实现可装配但仍需联调。这不是人天估算，也不是任务完成比例。P0为普通主链及基础接入优先，P1为营销/热点/外围及专项收口；正式全量交付仍需全部适用项完成。\n',
      '以下为核查中发现的明确缺口，不应归为“只改配置”：前1000候选及UM导入、模型固定方舟地址、部分旧OP结果/计数仍读Python历史业务表、Python最小DDL发布集、正式映射/策略审批、历史数据与同周期失败重建。普通人工计算是既有选中选题随机分配，并非V19自动匹配。\n',
      '## 3. 功能适配总览\n',
      table(['编号','功能域','功能','涉及工程','优先级','工作量','当前结论'],[[r['编号'],r['功能域'],r['功能'],r['涉及工程'],r['优先级'],r['工作量级别'],r['当前结论']] for r in rows]),
      '## 4. 逐项流程与适配内容\n',
    ]
    area=None
    for row in rows:
        if area!=row['功能域']:
            area=row['功能域'];sections.append(f'### {area}\n')
        sections.append(f'#### {row["编号"]} {row["功能"]}\n')
        sections.append(f'**涉及工程**：{row["涉及工程"]}。**优先级**：{row["优先级"]}。**当前结论**：{row["当前结论"]}。\n')
        for key in ('流程说明','交互方式','数据来源','数据去向','可复用实现','驻场适配工作','需行内提供'):
            sections.append(f'**{key}**：{row[key]}\n')
        sections.append(f'**主要工作量（{row["工作量级别"]}）**：{row["主要工作量"]}\n')
        sections.append(f'**验收标准**：{row["验收标准"]}\n')
        sections.append(f'**前置项**：{row["前置项"]}。\n')
        links=['['+path.split('/')[-1]+'](../'+path+')' for path in row['代码定位'].split(';')]
        sections.append('**代码定位**：'+' · '.join(links)+'。\n')
    sections += [
      '## 5. 七项原始资料能力\n',
      '这是SourceFacts内部读取能力，与历史IF/OP文档中的外部接口编号不是同一张表。本清单不擅自重命名已确认的IF/OP字段。完整字段以[查询契约](../java-backend/host-integration/BANK_SOURCE_CONTRACT.md)及[映射CSV](../java-backend/host-integration/BANK_SOURCE_FIELD_MAPPING.csv)为准。\n',
      table(['对应项','能力','输入','输出','交互','注意'],SOURCE_CAPABILITIES),
      '## 6. 九类调度适配\n',
      '宿主按平台支持情况合并或拆分Job，但必须推进全部适用角色。Java中没有迁入本地定时器；Python只在收到请求后受控执行持久化计算。Http202/accepted/processed均不能单独作为全业务成功信号。各角色的limit和游标并不完全一致，应按服务约定装配。\n',
      table(['Kind','用途','时机','数据流','推进/失败处理','对应项'],JOBS),
      '## 7. 数据归属与发布范围\n',
      '下面是14张Java业务表、3个同库视图及24项Python算法核心表族参考，另列行内原始资产。它不是经过现场审核的完整最小DDL清单；Python旧业务表、共享工作流与历史兼容依赖需要单独核查，不能据此物理删除旧表。新表/字段保留中文注释。\n',
      table(['位置','表/资产','用途','维护/写入方','发布注意','对应项'],DATABASES),
      'Java绑定六套Mapper XML：ManualMapper、BusinessPlanningConfigMapper、ConfigReleaseMapper、AutoScheduleMapper、PlanningQueryMapper、SlotCompletionMapper。BankSourceMapper是原始资料读取占位，绑定资料所属数据源，不混入策划业务会话。MyBatis已实现，现场主要是绑定宿主会话/事务、SQL和依赖兼容，不重写Repository。\n',
      'Python配置按现有godp_system_config管理，数据库启动连接按行内要求注入；若宿主要求统一配置中心/密钥管理，明确桥接方式，不在此擅自改变所有配置的权威来源。正式策略、词表、模型及向量维数必须匹配；不复制行外测试策略ID或历史批次ID作为生产常量。\n',
      '## 8. 需要行内共同确认的事项\n',table(['编号','事项','影响','对应项','需确认问题','配合方','不满足时的影响'],BLOCKERS),
      '## 9. 推荐驻场实施顺序\n',table(['阶段','目标','做什么','对应项','阶段出口'],PHASES),
      '进场前即可处理D01/D02/D03的服务端查询/UM解析、E01模型网关可替换客户端、I01～I03正式OP收口、A07最小DDL依赖核查和离线包准备；这些不依赖真实表名，适合行外先补。真实表SQL/私有SDK、网络开通与内容侧开发则依赖行内配合。\n',
      '## 10. 现场交付与验收证据\n',
      '每项完成时在Excel填写现场状态、负责人、行内配合人、实际改动文件、验收证据及备注。核心验收记录应包括：实际输入范围、身份/机构、业务/算法版本、请求/任务/槽位关联、源数据样本及结果数量、失败原因、重试幂等及导出对账；敏感资料只留行内。各工程筛选页是总表镜像，记录进度以适配总表为主。\n',
      '推荐分段：离线固定回归 → 七能力只读样本 → 普通人工 → 一个账号一个周期普通自动真实模型/双库 → 3～5账号质量 → 真实内容 → 营销/热点 → 权限/容量/恢复。只读返回空不算字段验收通过；不能将合成模型响应、H2或本地模拟内容验收写成真实行内全链通过。\n',
      '本轮只核查代码并生成文档/清单，未修改业务代码、调用模型、启动调度、读写数据库或自动提交GitHub。\n',
      '## 11. 核查依据\n',
      '- 当前三个工程源码及公开依赖清单；[当前实现状态](CURRENT_STATE.md)。\n- [宿主装配模板](../java-backend/host-integration/README.md)、[上下文/响应/分页说明](../java-backend/host-integration/REQUEST_CONTEXT_RESPONSES_PAGING.md)。\n- [统一资料链路](统一资料链路_2026-11-03.md)、[完整测试链路](全流程测试与行内接入对照_V1.0_2026-11-03.md)、[统一测试工具](../testing/README.md)。\n- 客户提供的工程侧技术.md及前端/大模型技术材料。材料中Parent/BOM/SDK版本是调研依据，不替代实际effective POM、前端lock和Python镜像依赖。历史V0.1迁移清单中尚未迁移的描述，以当前源码和本清单为准。\n',
    ]
    path=ROOT/'docs'/f'{STEM}.md';path.write_text('\n'.join(sections),encoding='utf-8')
    return path


def render_xlsx(rows):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment,Border,Font,PatternFill,Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    wb=Workbook();wb.remove(wb.active)
    editable=['现场状态','负责人','行内配合人','实际改动文件','验收证据','备注']
    widths={'编号':10,'功能域':16,'功能':32,'涉及工程':21,'流程说明':56,'交互方式':50,'数据来源':44,'数据去向':46,
            '可复用实现':43,'驻场适配工作':58,'需行内提供':49,'主要工作量':56,'工作量级别':13,'当前结论':34,
            '验收标准':56,'代码定位':64,'前置项':22,'优先级':12,'现场状态':17,'负责人':15,'行内配合人':18,
            '实际改动文件':36,'验收证据':38,'备注':40}
    def sheet(name,headers,records,tracking=False):
        ws=wb.create_sheet(name);ws.append(headers);ws.freeze_panes='E2' if tracking else 'A2';ws.sheet_view.zoomScale=80
        ws.row_dimensions[1].height=31
        for row in records:ws.append(row)
        ws.auto_filter.ref=ws.dimensions;ws.sheet_properties.pageSetUpPr.fitToPage=True
        ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
        ws.print_title_rows='1:1';ws.print_options.horizontalCentered=True
        for i,header in enumerate(headers,1):
            ws.column_dimensions[get_column_letter(i)].width=widths.get(header,45)
            ws.cell(1,i).fill=PatternFill('solid',fgColor='24398B');ws.cell(1,i).font=Font(name='微软雅黑',bold=True,color='FFFFFF',size=11)
            ws.cell(1,i).alignment=Alignment(vertical='center',wrap_text=True)
        for n in range(2,ws.max_row+1):
            ws.row_dimensions[n].height=100 if tracking else 64
            for c in ws[n]:
                c.font=Font(name='微软雅黑',size=10,color='243247');c.alignment=Alignment(vertical='top',wrap_text=True)
                c.border=Border(bottom=Side(style='hair',color='D9E1ED'))
                if n%2==0:c.fill=PatternFill('solid',fgColor='F2F5FA')
                if str(c.value).startswith(('=','+','@')):c.data_type='s'
            if tracking:
                ws.cell(n,headers.index('工作量级别')+1).font=Font(name='微软雅黑',bold=True,color='BC3131' if ws.cell(n,headers.index('工作量级别')+1).value=='高' else '9A6500')
        if tracking:
            col=get_column_letter(headers.index('现场状态')+1)
            rule=DataValidation(type='list',formula1='"待确认,待行内提供,待开发,待装配,联调中,待验收,已验收,不适用"')
            ws.add_data_validation(rule);rule.add(f'{col}2:{col}{ws.max_row}')
            ws.sheet_properties.tabColor='2F4BE0'
        return ws
    summary=[['用途','52项功能/流程驻场适配；包含交互、数据来源去向、主要工作量、依赖、代码定位和验收。'],
             ['基线','2026-11-03当前工作区；含未提交修改；不是已部署/真实行内验收结论。'],
             ['进度填写','只在适配总表填写现场状态和责任/证据；三个工程页为静态筛选镜像，不会自动回写。'],
             ['计数','跨工程项在前端/Java/Python页重复出现，不可将各页条数累加为工作量。'],
             ['工作量级别','高=跨团队/资料/权限或需补开发；中=已有实现但需装配联调；不是人天估算。'],
             ['优先级','P0=普通主链及基础接入；P1=营销/热点/专项收口；完整交付仍须完成全部适用项。'],
             ['权威来源','Java写业务库，Python写算法库，原始事实由行内维护；Python经Java HTTP查询。'],
             ['内容边界','内容侧读授权策划表/视图及营销需求，自行生产/审核/分配；Java查询状态，不新增Python领取/回调系统。'],
             ['明确缺口','前1000候选/UM批量解析、固定方舟模型地址、部分旧OP、最小算法DDL、正式映射策略和失败重建。'],
             ['边界','真实SSO、机构权限、模型出口、真实内容方及调度仍待行内；合成/H2验证不等于真实上线验收。'],
             ['维护','CSV是52项功能源数据；渲染工具检测到总表已填写跟踪信息时拒绝覆盖。现场跟踪表建议另存行内文件，工程页为生成时静态镜像。']]
    sheet('阅读说明',['项目','说明'],summary)
    keys=['编号','功能域','功能','涉及工程','优先级','工作量级别','当前结论','驻场适配工作','主要工作量','流程说明','交互方式','数据来源','数据去向','可复用实现','需行内提供','验收标准','前置项','代码定位']
    headers=keys+editable
    records=[[r[h] for h in keys]+['待确认','','','','',''] for r in rows]
    sheet('适配总表',headers,records,True)
    for project in ('前端','Java','Python'):
        sheet(project,headers,[record for r,record in zip(rows,records) if project in r['涉及工程']],True)
    sheet('资料能力',['对应项','能力','输入','输出','交互','注意'],SOURCE_CAPABILITIES)
    sheet('调度任务',['Kind','用途','时机','数据流','推进/失败处理','对应项'],JOBS)
    sheet('数据归属',['位置','表/资产','用途','维护/写入方','发布注意','对应项'],DATABASES)
    sheet('待确认事项',['编号','事项','影响','对应项','需确认问题','配合方','不满足时的影响'],BLOCKERS)
    sheet('实施顺序',['阶段','目标','做什么','对应项','阶段出口'],PHASES)
    path=ROOT/'docs'/f'{STEM}.xlsx';wb.save(path);return path


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    existing=ROOT/'docs'/f'{STEM}.xlsx'
    if existing.exists():
        from openpyxl import load_workbook
        wb=load_workbook(existing,read_only=True,data_only=False)
        try:
            ws=wb['适配总表'];values=ws.iter_rows(values_only=True);columns=list(next(values))
            for record in values:
                for field in ('现场状态','负责人','行内配合人','实际改动文件','验收证据','备注'):
                    current=record[columns.index(field)]
                    if current not in (None,'','待确认'):
                        raise ValueError('Workbook contains on-site tracking data; refusing to overwrite it')
        finally:wb.close()
    rows=load_rows();md=render_md(rows);xlsx=render_xlsx(rows)
    for link in re.findall(r'\]\(([^)]+)\)',md.read_text(encoding='utf-8')):
        if not (md.parent/link).exists():raise ValueError('Broken documentation link: '+link)
    print(f'Rendered {len(rows)} items, {len(SOURCE_CAPABILITIES)} source capabilities, {len(JOBS)} task kinds, 10 workbook sheets.')
    print(md.relative_to(ROOT));print(xlsx.relative_to(ROOT))


if __name__=='__main__':main()
