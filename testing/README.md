# 行外固定数据与统一回归

另有显式真实环境入口`python -m testing.live --execute`，调用模型并写两个测试库，不属于本目录默认离线回归。准备、暂停本地调度及边界见[全链路验收](../docs/普通自动策划全链路验收_2026-11-03.md)；已完成任务可用`python -m testing.live_verify <目录>`只读核查页面和导出。

本目录只用于开发和验收，不导入运行服务、不向业务库初始化数据。合成账号、选题、向量和模型响应均已固定；没有真实客户资料、模型密钥或数据库密码。

日常outside与完整闭环已使用同一个Java资料入口，不再启动临时资料服务器。`source_fixtures`只负责准备Java读取的模拟文件，`live_server`只限制本轮账号/选题范围，不更换取数协议。可运行`python -m testing.source_verify`只读核查分页、鉴权、页面资料及历史查询，不调用模型、不新建任务。详见[统一资料链路](../docs/统一资料链路_2026-11-03.md)。

## 常用命令

在仓库根目录执行，先安装开发依赖：

```bash
python -m pip install -r python-backend/requirements-dev.txt
```

首次开发环境还需准备兼容的JDK/Maven、Node和前端依赖。统一回归不会自动安装依赖。Java默认使用Maven离线模式；缺少工具或缓存必须明确失败，不能跳过后显示通过。

```bash
# 小集：算法回放 + Python + 工具自测 + Java + 前端测试与构建
python -m testing

# 只看算法：5个账号、60个选题、15条策划
python -m testing --suite algorithm

# 规模集：100个账号、600个选题、300条策划
python -m testing --suite algorithm --dataset scale

# 可分别验证某个工程
python -m testing --suite python
python -m testing --suite java --maven /path/to/mvn --java-home /path/to/jdk
python -m testing --suite frontend
```

Windows的`--maven`填写`mvn.cmd`路径。未显式指定时优先使用PATH和JAVA_HOME；本仓库行外已有的`.tmp-tools`也可被识别，不随Git或驻场部署。

新环境先在允许联网的行外准备好Maven依赖。仅在需要解析依赖时添加`--allow-dependency-network`；这不会启用模型调用。前端依赖需提前`npm ci`。

## 数据集覆盖

`data/small.json`和`data/scale.json`是已冻结的实际数据，正常运行直接读取，不临时生成。`manifest.json`记录完整语义JSON的SHA-256，发现数据被修改即停止。

- 五个生命周期、认证/非认证账号、合成属主UM号、十二类选题二级分类。
- T3/T4/T5层级标签、人设映射、T6需求及固定8维合成向量。
- 固定周一/三/五日期，不依赖“今天”，避免下周重跑结果改变。
- 历史已用、适用范围不符、未知主标签、关联标签OFF、模型DROP和条件适配通过/不通过。
- 过期、营销、停用三类源选题留在原始样例中，但在预声明的冻结候选范围之外。它们用于检查输入集合；不把这种预声明过滤冒充真实行内适配或真实来源过滤验收。

数据和映射由开发规则构造，**不是客户确认的金标**。真实打标、真实向量与模型Prompt效果不属于这轮离线回放结论。

## 实际执行哪些代码

仅运行V19，调用现有`execute_quality_job`，包括映射、五路召回、精判门槛及组合分配；仅替换模型响应、向量读取、缓存、心跳和报告持久化边界。没有另外写一个“看起来像算法”的分配器。

算法回放进程禁止网络和MySQL连接。Python单测通过`testing.pytest_plugin`运行：提供独立系统配置、禁止真实MySQL和公网，仅允许测试HTTP夹具使用回环地址；系统配置存储专项测试使用其自己的数据库替身。Java入口显式关闭真实双库和HTTP验收开关，默认`mvn -o test`。前端只运行已有测试和静态构建。

不启动/停止本地服务，不唤醒运行任务，不修改库内策略，也不自动运行收费模型。

## 如何看报告

每轮输出独立目录`run/regression/<时间戳>/`：

| 文件 | 用途 |
| --- | --- |
| `summary.json` | 各工程、工具、算法步骤及总结果 |
| `report.html` | 电脑直接打开；查看指标、约束、基线差异、V19与历史基线对照，并按账号查看逐条策划 |
| `report.md` | 精简报告，方便附在交付记录 |
| `algorithm.json` | 完整策略、输入指纹、算法代码指纹、结果、V19召回/精判证据和基线差异 |
| `*.log` | 每个工程的测试或构建日志；异常时定位具体步骤 |

只运行某个工程时不会产生算法报告。`--output`可指定新目录，已有非空目录拒绝覆盖。

算法状态：`passed`无基线变化且门槛通过；`review`选择/分数/策略发生变化需人工复核；`failed`约束未通过；`incomparable`数据、模型空间或算法集合不同；`unbaselined`缺少基线。统一入口只有全部步骤`passed`才返回退出码0，其余均非0。

仅保留V19，与同一数据集的V19历史基线比较。耗时只供同机器观察，当前不作为跨机器硬门槛。

## 比较一次策略修改

准备一个本地JSON对象，仅用`v19`键放完整候选策略；可以从`data/small.json`的`policies`复制。未指定时沿用固定V19策略。

```bash
python -m testing --suite algorithm --candidate-policy run/candidate-policy.json

# 与前一轮完整算法报告比较
python -m testing --suite algorithm --baseline run/regression/上一轮目录/algorithm.json
```

相同数据才能比较。候选策略只在内存执行，不批准或替换数据库策略。即使总匹配数相同，只要具体选题发生变化，仍返回`review`供查看逐条变化。

确认为新的开发回归基线后，才显式记录：

```bash
python -m testing --suite algorithm --record-baseline
python -m testing --suite algorithm --dataset scale --record-baseline
```

这会更新`baselines/`，应单独审查并随代码提交。硬性约束失败时禁止记录。更新数据时先修改生成定义、显式执行`python -m testing.datasets --write`，再评审新数据指纹和基线；常规回归不会自动生成数据或接受新结果。

## 驻场怎么使用

在行外完成回归、算法对比并保存报告；交付固定Git版本、变更模块、数据库脚本和测试证据。行内重点验证实际资料/内容字段、身份权限、宿主MyBatis与事务绑定、真实模型和调度，不重复在现场调算法权重。

行内要跑这套测试，需另外准备目标系统兼容的Python wheels、Maven缓存/内网依赖及Node依赖；Windows环境不能直接搬到Linux。当前工具不宣称这些离线依赖已全部打包，也不替代真实行内集成验收。
