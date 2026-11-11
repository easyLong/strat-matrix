# BankSourceFacts：行内资料查询与字段映射契约

版本：V0.3，2026-11-11。本文件对应当前代码中的7项资料查询能力；沿用现有字段，不重新编排历史IF/OP编号。公共仓库保留稳定契约和SQL占位，现场表、字段及状态映射在私有XML中维护。

配套文件：[字段映射表（CSV）](BANK_SOURCE_FIELD_MAPPING.csv)、[Bean装配示例](BankSourceBindings.java.example)、[只读SQL占位](../godp-planning-services/src/main/resources/mapper/xiangliang/source/BankSourceMapper.xml)、[宿主装配说明](README.md)。CSV为UTF-8带BOM，可用Excel打开。

2026-11-11补充：提供 `BankSourceSqlAdapter.create(sourceDataSource, sourceTransactions, mapperXml, storageZone)` 统一装配。宿主传入资料库数据源、对应事务管理器及私有 XML 即可复用现有7类 POST 查询入口，无需再次编写 Controller。账号分页完成后，在同一只读事务内执行一次 `accountInteractions` 批量查询；空页不查互动。装配时检查所有11条语句，缺文件或仍有占位时启动失败，不回退模拟资料。

行外 Java 可显式选择 `planning.source.mode=sql`、`planning.source.mapper-location=file:/绝对路径/BankSourceMapper.xml`，存储时区配置为 `planning.source.storage-zone=Asia/Shanghai`。此模式复用行外业务数据源，仅用于资料表位于同一开发库的联调；默认仍为 `fixture`。行内使用上方装配示例传入宿主资料数据源，不加载行外连接池、模拟数据或自动建表。原始私有 SQL 不进入公共仓库；查询代码不创建表、不写原始资料。

查询接通与生产业务验收分开记录：`production-status` 的流水号关联、版本及内容范围，`marketing-status` 的任务号关联和完成数量，以及有效营销投放定义，都须与内容侧实际口径匹配。只能返回部分内容类型或固定版本的资料实现，不代表其他内容类型和重试版本也已验收。

2026-11-05补充：营销选题不要求标题和大纲；活动类提供关联活动ID、名称、活动所属组织，银行产品类提供关联产品名称与产品ID。新增映射字段为`related_activity_id`、`activity_organization`、`related_product_id`，已有名称字段继续使用`related_activity`、`related_product`。非营销标题仍必填，不将活动名称伪装成选题标题。详情、预选及任务快照透传这些字段，不新增数据库列。

人工策划有效期按北京时间的自然日期比较，起止日期均包含：非营销使用用户投放日期，营销使用当前日期。Java资料查询和Python目录投影不得先按“现在有效”删掉未来投放日可用的选题；候选页面按本次日期过滤，Java提交再次校验。单独算法召回的有效时点规则保持独立。

## 1. 数据经过哪里

```text
行内原始表/现有Service
  → BankSourceQueries（7个查询方法）
  → BankSourceFacts（请求、分页、关联及返回校验）
      + BankSourceMapping（字段、编码、时间转换）
  → Java页面资料/内容事实适配器 → Java业务库
  → Java内部资料HTTP → Python画像、打标、向量和匹配 → Python算法库
```

基础资料只查询，不复制维护一份原始表。生命周期、T1–T6、向量及匹配分数不要求行内原始表提供。策划正式结果仍由现有Java业务服务写入业务库；本适配器不写原始资料、不触发内容生成、不创建表或调度器。

日常outside默认使用`FixtureSourceFacts`，仅显式设置`planning.source.mode=sql`时加载私有XML。`BankSourceFacts`本身没有自动注册注解；inside由宿主显式注册唯一的`SourceFacts` Bean，避免未填SQL影响当前开发。

## 2. 驻场选择一种查询接法

| 接法 | 填写位置 | 共用不变的部分 |
| --- | --- | --- |
| 直接查询原始表 | `BankSourceMapper.xml`的11条SELECT：3组count/列表、4条列表查询和1条账号互动批量查询；注册到资料所属MyBatis会话 | 请求对象、字段映射、结果校验、业务适配器、Python契约 |
| 调用已有Service/RPC | 宿主新建一个`BankSourceQueries`实现，覆盖7个方法；返回`PageRows`或记录列表 | 同上，无需强行改成SQL |

SQL方式通过`BankSourceSqlAdapter`装配`MapperBankSourceQueries`，count、列表及本页互动在同一只读事务中执行。装配示例传入的`xiangliangSourceDataSource`和`xiangliangSourceTransactions`必须指向同一资料库；工厂基于传入数据源创建独立MyBatis会话，不创建连接池。它们与`xiangliangBusinessSessions`/业务事务可以不同。复用宿主已有资料会话时，也可手工构造查询器并调用`verifyWith`绑定该会话工厂。一个能力涉及多个既有服务或数据源时，优先在宿主查询实现中组合，不能给一个MyBatis事务随意混用数据源。

只读标记不是数据库权限控制。原始资料连接使用行内认可的只读权限；一致性隔离级别由宿主按数据库类型确定。需要跨页稳定快照时，由宿主提供相应读取保障，目前不声称OFFSET分页已具备快照能力。

未填写的SQL含明确的503保护。未覆盖的查询方法也返回503；不是空列表、不是自动退回模拟。真正执行成功且没有匹配记录时才返回空结果。

## 3. 查询输入与结果

已有内部HTTP入口：`POST /api/plan/internal/source/{能力}/query`，JSON请求体，`X-Integration-Token`服务身份认证。该入口是Java和Python之间的数据能力，不是新增一组供浏览器直连的接口。Java业务可以直接调用同一个`SourceFacts` Bean。

| 能力 / 方法 | 输入 | 返回 | 行内实现重点 |
| --- | --- | --- | --- |
| `accounts` / `accounts(Accounts)` | 可选页码、每页条数、更新时间范围、账号ID列表 | 账号分页，含互动明细 | SQL先过滤可参与策划资格和权限，再count及分页；一行一个账号 |
| `topics` / `topics(Topics)` | 可选页码、每页条数、更新时间范围、选题ID列表、选题来源、选题类型、仅可用、有效时点 | 普通/热点及营销/非营销选题分页 | 普通/热点是来源；营销/非营销是类型；不要混成同一枚举 |
| `marketing-contents` / `marketingContents(Marketing)` | 必填账号ID；可选页码、每页条数 | 已审核通过、可引用的营销内容分页 | 先过滤账号归属、过审和可用资格；按审核通过时间、内容ID升序 |
| `effective-marketing` / `effectiveMarketing(Placement)` | 必填账号ID、投放日期 | 当日有效营销投放记录列表 | 有效投放以内容侧事实为准，不能把“已生产”当成“已有效投放” |
| `production-status` / `productionStatus(Production)` | 必填`slot_ids`，1～500个 | 槽位内容生产状态列表 | 按槽位ID及版本关联；同槽位同版本仅一条最新事实 |
| `marketing-status` / `marketingStatus(MarketingStatus)` | 必填`task_codes`，1～500个 | 营销任务进度列表 | 每任务一条最新事实；生产完成与审核通过分开 |
| `marketing-allocations` / `approvedDemandContents(ApprovedDemand)` | 必填`task_code` | 已过审且已分配到账号的营销内容列表 | 包含账号及内容ID；按审核通过时间、内容ID升序，后续Java确定投放日 |

`topic-usage`虽然也经过内部资料Controller，但查询的是策划业务库使用次数，不属于行内原始资料查询，也不加入这7个方法。

### 分页及时间的精确定义

| 中文字段 | 代码字段 | 约定 |
| --- | --- | --- |
| 页码 | `page_no` | JSON整数，默认1，最小1 |
| 每页条数 | `page_size` | JSON整数，默认100，最大500 |
| 更新开始时间 | `updated_from` | 可空，包含边界；完整日期时间 |
| 更新结束时间 | `updated_to` | 可空，不包含边界；有起止值时起点须早于终点 |
| 账号ID列表 / 选题ID列表 | `account_ids` / `topic_ids` | 可空，最多500个字符串ID；未传/null为不限定，显式空数组为不查任何对象；重复ID按首次出现去重 |
| 选题来源 | `source` | `普通`、`热点`；不传表示不限定 |
| 选题类型 | `topic_type` | `营销`、`非营销`；不传表示不限定 |
| 仅可用选题 | `available_only` | 布尔值，默认false；true时先过滤不可用，再count和分页 |
| 有效时点 | `valid_at` | 完整日期时间；有效开始≤该时点≤有效结束；空端点视为未限定该端 |
| 账号ID | `account_id` | 非空字符串，最长64；用于营销内容和有效投放查询 |
| 投放日期 | `publish_date` | `YYYY-MM-DD`，不是投放时刻 |

代码字段为模块内部稳定契约，不要求行内数据库改列名。请求支持表中中文别名；同一字段中英文同时传入且值冲突会拒绝。未约定的输入字段返回422，避免接错字段后悄悄失效。营销内容查询当前运行契约只有账号及分页，没有更新时间筛选；如后续增加，应同时修改两端契约并补测试。

分页返回固定形态：

```json
{"items": [], "total": 0, "page_no": 1, "page_size": 100}
```

`total`是**应用全部资格、查询条件与数据权限后的总条数**。列表必须SQL侧分页：`offset=(page_no-1)*page_size`，账号按账号ID、选题按选题ID稳定排序。不能先分页再去掉不可参与账号，不能由明细联表把一个账号拆成多行。互动明细建议对本页账号一次批量查询组装，避免逐账号查询和联表膨胀。

总数与页内条数必须一致；越界页为`items=[]`并保留实际total。校验不会帮SQL“修正”错误total或吞掉不合格账号，而会返回502。更新开始/结束采用`[开始, 结束)`；比较按同一瞬时，不按时间字符串排序。裸日期不接受为更新时间。无时区的完整请求时间按北京时间解释；返回统一为带`+08:00`的ISO日期时间。

多页抓取时建议固定本次更新时间上界，避免扫描期间不断进入新记录；它不能替代原始库一致性快照。账号、人设、组织和互动来自不同表时，现场需确认组合更新时间如何反映这些资料变化。禁用账号按现有口径不返回，调用方不能把“本次未出现”当成一条显式禁用事件。

## 4. 返回字段与映射

完整67项对象字段（含嵌套及不同能力重复字段）见[映射CSV](BANK_SOURCE_FIELD_MAPPING.csv)，不是要求行内新增67列。现场只填写“行内表/服务、行内字段/取值、现场转换说明、确认人/日期”；不要把真实内部表结构提交公共仓库。

| 对象 | 包含字段 |
| --- | --- |
| 账号 | 账号ID、昵称、属主UM号、属主组织、平台、账号类型、可参与策划、粉丝量、账号信息更新时间、人设、性别、兴趣爱好、表达风格、近三个月内容互动明细 |
| 互动明细 | 内容ID、账号ID、发布时间、标题、点赞数、收藏数、评论数、互动数据更新时间 |
| 选题 | ID、来源、类型、标题、大纲、二级分类、热度、可用状态、有效起止时间、更新时间、关联产品/活动/属地热点 |
| 过审营销内容 | 内容ID、绑定账号ID、标题、正文、关联产品/活动、审核通过时间 |
| 有效营销投放 | 投放记录ID、账号ID、内容ID、投放日期 |
| 槽位生产状态 | 槽位ID、版本、内容ID、内容状态、状态更新时间、生产任务ID、失败原因 |
| 营销任务进度 | 任务号、内容状态、完成数、失败数、已分配账号数、状态更新时间 |
| 过审分配内容 | 任务号、内容ID、绑定账号ID、标题、正文、二级分类、审核通过时间 |

仍不包含业务线、地域、分享数。属主组织应由行内查询返回符合页面要求的组织名称（最小到二级分行），适配器不根据名称猜测组织层级。T1–T6等算法产物由Python生成。

### 转换规则

1. SQL用`AS account_id`等代码别名或CSV中的中文别名返回；已有Service可组装同样的Map。注意数据库驱动的别名大小写，必要时使用该数据库的引用标识符保留小写；Map键须与清单一致，不猜测大写列名。额外数据库列不会转发给Python/页面，两种别名同时出现冲突会拒绝。
2. ID必须为字符串，保留前导零。数值型主键在源查询显式转文本，不根据Java数值自动猜测原ID格式。槽位ID最长128，其余关联ID最长64。
3. 账号类型只接收`认证/非认证`或现有布尔表示。参与资格/选题可用支持Boolean、0/1或true/false文本；其他行内码可通过`BankSourceFieldRules`集中配置，或由SQL CASE/宿主查询实现映射，不默认视为正常。
4. 选题类型与来源枚举严格校验；内容状态按下一节转换。账号性别M/F归一为男/女，其他文本原样返回。兴趣爱好为文本数组或JSON数组；不自动拆逗号文本。
5. 时间支持JDBC Timestamp、带时区时间、完整时间文本。`BankSourceMapping(storageZone)`显式指定数据库DATETIME的存储时区，默认北京时间；不同源时区应先在宿主统一。不要依赖服务器默认时区解释数据库业务时间。
6. 未知粉丝量和互动计数为null，不补0；未知文本为空字符串，数组为空数组。必填字段缺失直接报错；缺失账号类型保持null，不能当成非认证。传输可选不等于业务必然可用，缺少画像、资格或统计依据时仍应按业务要求补齐。
7. 营销内容必须先由源查询确认审核通过且可引用；仅有`approved_at`不意味着代码能推断行内审核状态。普通/热点用选题ID，已生成营销内容用内容ID，不能互换。

`slot_id`、`version`、`task_code`是策划侧定义的关联信息，内容侧需在生成/分配记录中保留或可查询映射。行内若仅有`production_task_id`，现场需补到槽位/版本的映射查询；不能把生产任务ID直接充当槽位ID。没有这些关联时，状态对账并未完成对接。

## 5. 状态和空值

| 返回对象 | 接受的状态 | 特别校验 |
| --- | --- | --- |
| 槽位内容 | 待生产、生产中、已完成、生产失败 | 版本≥1；已完成必须有内容ID |
| 营销任务进度 | 待分配、待生产、生产中、已完成、生产失败 | 各数量非负；已完成不能仍含失败数 |

热点“待定题”是策划内部尚未关联内容的阶段，不要求内容侧返回“待定题”。营销生产状态“已完成”也不能代替过审分配事实，两者使用不同查询能力。

无投放、无过审分配、尚无内容状态记录时允许返回空列表；已知记录不能用缺失状态或“未知”代替真实状态。状态查询可只返回已找到的关联记录，缺失记录继续等待。相同`slot_id+version`不能返回多条；不同历史版本允许返回，业务对账会忽略过期版本。分页记录、任务进度、有效投放及过审内容按各自业务ID查重，且返回账号/日期/任务/ID必须处于请求范围内。

| 情形 | HTTP状态 / 处理 |
| --- | --- |
| 参数类型、范围、字段不符合契约 | 422，不进入原始查询 |
| 内部令牌缺失/错误 | 401，不进入原始查询 |
| 未实现查询、未填写SQL、原始资料暂不可用 | 503；不返回假空结果 |
| 必填字段缺失、未知状态、重复或越范围记录、分页不一致 | 502；提示接入返回不符合契约 |
| 查询成功且无匹配记录 | 200及真实空结果 |

SQL/Service底层异常不把私有SQL、连接信息直接放进HTTP错误；具体诊断由宿主内部日志及链路追踪完成。宿主实现抛出的`BusinessException`消息也必须遵守不泄露私有资料的约束。

## 6. 权限及维护边界

- 页面调用先由宿主`HostAccess`建立可信用户与机构范围；SQL/现有Service必须实际应用范围，count和列表保持同一范围。该范围不能来自浏览器自报的组织筛选参数。
- Python内部查询使用服务身份；所能查询的数据集合由行内为算法任务授权，不把机器令牌当成全部业务数据的无条件放行。宿主需分别确认页面身份和算法身份如何落实资料权限。
- 策划侧维护本契约、映射校验和测试。行内提供表结构、状态码、权限方式及原始事实；双方驻场完成真实SQL/Service绑定，之后由行内工程负责私有查询与发布。
- 业务数据源与Python算法库继续隔离。Python通过Java资料HTTP读取，不能因SQL适配方便而直接连接行内业务库。

## 7. 已有测试与现场验收

```bash
# java-backend目录；H2和HTTP响应桩，无MySQL/模型调用
mvn test -Dtest=BankSourceFactsTest,BankSourceSqlTest,BankSourceIntegrationTest,BankSourceFieldRulesTest

# 仓库根目录，统一回归，包含下面的跨语言契约校验
python -m testing
```

覆盖7能力字段转换、分页/半开更新时间、真实H2 MyBatis参数绑定与资格过滤、11个SQL占位拒绝执行、只读事务、内部鉴权、错误隔离、Java→Python投影和Java/Python共用JSON结构。响应样例在[test fixture](../godp-planning-server/src/test/resources/bank-source/contract-sample.json)，全为合成资料。

### V0.2：减少现场重复代码

**字段名、状态码集中配置。** 新增`BankSourceFieldRules`，装配时传给`BankSourceMapping`。示例见[现场映射配置](BankSourceSiteMapping.java.example)，不新增配置表或管理页面。

```java
BankSourceFieldRules rules = BankSourceFieldRules.builder()
    .alias(BankSourceMapping.Kind.ACCOUNT, "nickname", "HOST_DISPLAY_NAME")
    .code(BankSourceMapping.Kind.PRODUCTION, "status", "DONE", "已完成")
    .build();
BankSourceMapping mapping = new BankSourceMapping(ZoneId.of("Asia/Shanghai"), rules);
```

上例列名/编码是合成示例，不代表行内真实值。已经用标准SQL别名输出的字段无需再配alias。规则按对象区分，内容状态不会误用于营销任务状态。映射为不可变快照，不会随Builder后续更改；字段名拼错、同列映射到多个字段、占用其他契约列、重复编码会在装配时拒绝。配置了编码映射的字段，只接受明确配置的源编码，**不自动放行未配置的编码**；转换结果仍须通过原类型、状态和范围校验。不改变7项查询及67项对象字段。

**互动明细统一批量装配。** 直接查表时，可使用`MapperBankSourceQueries`四参数构造器：

```java
BankSourceQueries queries = new MapperBankSourceQueries(
    sourceMapper, sourceTransactions, mapping,
    ids -> interactionService.findByAccountIds(ids)); // 宿主实现本页账号的批量查询
SourceFacts facts = new BankSourceFacts(queries, mapping);
```

`interactionService`仅为宿主实现占位，未在本项目伪造。每个非空账号页只调用一次批量查询，与账号count/列表共享只读事务；同一Mapping实例同时用于关联识别及最终转换。它在Map层组装，不增加第8个资料能力，不增加基础表。

批量函数返回本页账号的近三个月互动行；时间窗口、权限及各平台原始计数口径由宿主SQL/Service落实。工具保留total和账号顺序，补齐无互动账号的空数组，拒绝越范围账号、重复账号/内容及null查询结果，不修改源Map。提供批量函数时会替换该页已有互动字段，避免旧数据混入。如果已有Service一次就返回完整嵌套实体，无需启用这个可选功能。已有Service也可直接调用`BankSourceInteractions.attach`，需要一致性时由宿主管理外层只读事务。远程Service不因Java事务包裹而自动拥有同库快照保证。

**同一只读验收工具用于行内与行外。** 见[使用步骤](../../testing/README.md#资料适配只读验收)。入口为`python -m testing.bank_source`，只访问Java内部资料查询，不加载开发数据库、模型或私有启动配置，也不依赖公网。需要Python环境中已有的Pydantic依赖。

工具先确认无令牌请求被拒绝，再逐项校验7项能力的合成或现场样本。必须明确填写样本ID，每页最多50条，最多3页；只发有限查询，不循环全量扫描。空数据、未填写能力与失败分别标记，只有7能力都有样本通过才返回passed。报告只记录能力、数量、字段路径和错误类型，不保存账号/选题正文、请求参数、令牌或远端错误正文；报告仍按行内测试资料管理。

它验证的是所选样本及有限分页，不能替代机构权限、全部状态分支、完整数据范围和性能验收。网络HTTP302不跟随，不继承行外代理，连接错误和服务器报错不泄露原始响应。无需为该工具增加生产诊断Controller。

驻场按顺序完成：

1. 填写映射CSV，确认原始资料源、资格/审核/有效投放口径、时间精度、组织名称和关联ID。
2. 装配一个`BankSourceFacts` Bean，填写SQL或7方法实现；检查全部占位已替换，关闭outside组件。
3. 验证count/分页、更新时间边界、禁用账号排除、权限范围；检查互动分页不丢失、不重复、不产生逐行SQL。
4. 验证营销先过审优先、当日有效投放、生产版本及任务关联、尚无状态返回空和失败状态显示。
5. 跑inside三页面与普通策划闭环，再跑真实内容及热点/营销分支。真实行内SQL、SSO权限、调度及性能仍须现场验证，本轮测试不替代这些验收。
