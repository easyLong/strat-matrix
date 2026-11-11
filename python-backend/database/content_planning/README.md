# 策划模块数据库交付边界

应用导入、独立启动和宿主安装均不执行 DDL、升级、配置初始化或演示数据写入。生产由 DBA 审核执行脚本，应用使用 DML 账号。`schema.sql` 等保留兼容部署的完整源定义，**不能将整个目录中的 SQL 无差别执行到算法库**。

## 安装与升级

- 基础配置数据使用当前数据库快照，见[行内基础数据初始化清单](../../../docs/行内基础数据初始化_2026-11-11.md)。只读导出工具为 `tools.content_planning.export_foundation_data`；标签、人设映射、算法规则及业务规则保留实际版本和状态，不从示例重新生成。

- 首次算法库安装入口：`algorithm_schema.sql`，仅包含 25 张算法自有表，无 Java 业务表、原始资料表或策略自动批准。
- `CREATE TABLE IF NOT EXISTS` 不升级已有字段。已有环境须结合 `migrations/` 和原发布版本逐项审核，尤其公共审计字段迁移；本次包路径调整本身不要求新增业务字段。
- 配置缺项初始化是独立的显式步骤：`python -m tools.content_planning.initialize --apply --resource-directory <绝对目录> --config-file <宿主配置JSON>`。该命令会建表并补缺失配置键，不导入历史凭据，不创建演示数据。行内优先交 DBA 执行，不授予应用 DDL 权限。
- 本次未执行线上建表、迁移或数据写入。MySQL DDL 自动提交，初始化失败可能部分生效，必须核查后续作业的依赖。
- 回退模块代码前，停止新任务受理，等待受控执行完成并保留持久化检查点；还原旧代码包/原启动入口和依赖。不要自动删除表、快照、提案或已写业务结果。数据库回退须使用该次升级单独审查的脚本与备份；此轮无数据库结构变更。

## 算法表与功能

| 功能 | 算法自有表 | 外部依赖 |
| --- | --- | --- |
| 连接配置、规则、词表及版本 | godp_system_config、godp_strategy_config、godp_strategy_config_version、godp_algorithm_config_command | 宿主可显式覆盖连接配置；算法版本仍在 MySQL |
| 标签、画像、映射及向量 | godp_topic_tag、godp_topic_tag_history、godp_t6_tag、godp_topic_profile、godp_account_profile、godp_topic_label_job、godp_account_mapping_rule | Java 账号/选题资料查询、文本/向量模型 |
| 输入准备及冻结 | godp_ai_preparation、godp_ai_preparation_account、godp_ai_preparation_topic、godp_ai_preparation_progress | Java 基础资料、带版本的业务配置；下述正式批次校验仍需兼容结构 |
| 策略、匹配和可复用模型结果 | godp_matching_policy、godp_matching_task、godp_matching_input_snapshot、godp_matching_attempt、godp_matching_ai_cache、godp_matching_quality_run | 已批准 V19 策略、同一向量空间及模型网关 |
| 推进、提案、人工计算 | godp_planning_pipeline_run、godp_planning_stage_run、godp_algorithm_proposal、godp_manual_compute | Java 提交输入、获取提案、幂等落业务库并确认；行内调度触发唤醒 |

## 仍存在的兼容依赖，不能忽略

| 路径/分支 | 实际依赖 | 接入约定 |
| --- | --- | --- |
| `ai_preparation.assert_no_result_batch()` | 读取 `godp_planning_batch` 检查同周期已有正式结果 | 此校验仍被准备链调用；不能删掉校验来掩盖缺表。仅有 25 表的目标环境需要后续用 Java 幂等查询契约替换并验收 |
| `ordinary_scheduler.start_v19_pipeline()` | 读取 `godp_auto_plan_run` | Java 调度所有权下旧 Python 自动调度入口不执行；若启用兼容入口仍需原结构 |
| `planning_result_commit.commit_pipeline_result()` | 读写 `godp_planning_batch`、`godp_planning_item`、`godp_slot_state`、`godp_auto_plan_run` 等 | 仅 Python 提交所有权的兼容分支。目标保持 Java 落业务结果；提案/确认走已有哈希和幂等契约，不跨库补写 |
| 旧 Python 页面查询、营销/热点业务、导出与演示 CLI | 完整业务结构及部分历史资料结构 | 默认宿主交付不开放旧 Python 页面接口；当前 Vue 仍通过 Java，兼容 CLI 必须按其部署环境显式使用 |

`sql-dependencies.json` 是离线静态 SQL 字符串扫描，列出文件及表归属，包括历史/工具分支；不能证明某功能已完成真实双库端到端验收。动态 SQL 可能需要补核。

## 必需 Java 能力

原始账号、人设/互动、普通/热点选题、营销内容及生产状态均由既有 Java HTTP 资料契约提供；Java 负责业务配置、调度、持久化任务及最终业务结果。Python 只通过适配器读取资料，不因同进程安装而获得 Java 库访问权。所用路径、请求模型和鉴权详见模块 OpenAPI 与 `bank_bridge/contracts.py`；Java 基础地址须按部署环境配置。

25 表就绪检查仅表示算法自有结构存在；完整业务链上线还须满足上列功能对应依赖。目标宿主若只允许 25 表，本轮不能据此宣称准备→正式结果全链已完成改造。
