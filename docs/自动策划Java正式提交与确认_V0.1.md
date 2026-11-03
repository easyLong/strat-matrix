# 自动策划 Java 正式提交与确认 V0.1

日期：2026-11-03。本轮完成普通自动策划提案由 Java 落库、Python 接收确认及失败恢复的代码与隔离测试。运行中的数据库和服务尚未切换，自动调度开关继续关闭。

## 当前链路

```text
宿主 Job → Java 周策划任务 → Python Pipeline（commit_owner=java）
                               ↓ 组合完成后等待业务提交
Java 获取冻结算法提案 ← Python godp_algorithm_proposal
  ↓ 校验指纹、版本、周期、账号日期覆盖和热点比例
同一业务库事务：批次 + 全部槽位 + 任务提交凭证（待确认）
  ↓ 事务提交后才发送确认
Python 确认提案指纹和 Java 批次号 → 保存算法引用、完成 Pipeline
  ↓
Java 任务已完成；账号／周期／批次查询复用原 Java 结果服务
```

每个 Pipeline 创建时固定 `commit_owner`，默认 `python` 兼容已有任务；Java 专用自动策划启动入口创建 `java` 归属任务。归属不同的任务不能复用同一周期。Python Worker 遇到 Java 归属时停在 `result_commit` 阶段，旧正式提交函数也会拒绝代写；当前不开放这些任务的 Python 取消入口，防止已发出的提案与 Java 提交发生竞态。

## 两个内部调用

| 方法与路径 | 输入 | 输出及用途 |
| --- | --- | --- |
| `POST /api/internal/planning-pipelines/{id}/proposal` | `business_config_version`、`business_config` | `schema_version`、`proposal_json`、`proposal_hash`。首次调用将算法提案冻结到算法库，以后返回同一原始 JSON；配置或版本不符时拒绝 |
| `POST /api/internal/planning-pipelines/{id}/acknowledgement` | `proposal_hash`、`business_batch_id` | `status=accepted`、`pipeline_id`、原指纹、批次号、`reused`。同凭证重复确认成功，不同批次或指纹冲突 |

两条接口都沿用内部令牌校验。Java 对 `proposal_json` 的原始 UTF-8 字节计算 SHA-256，再解析和校验对象，避免 Java／Python 浮点及 JSON 格式差异导致误判。提案包含算法策略及匹配任务指纹、账号快照、完整槽位安排、热点普通选题兜底。Java 使用当前任务里冻结的业务配置比较，不读取后来修改的配置。

## 幂等与恢复

| 场景 | 行为 |
| --- | --- |
| 两个宿主同时提交同一任务 | 业务任务行锁串行处理，第二次复用同一批次；批次内槽位唯一约束继续生效 |
| 任一槽位写入失败 | 整个业务事务回滚，批次、明细和待确认凭证均不残留，下次调度重新提交 |
| Java 落库后进程退出／确认网络失败 | 任务已是“待确认”；后续调度只发送已保存指纹和批次号，不重新获取提案、不重复落库 |
| Python 已接受确认但响应丢失 | 再次确认返回 `reused=true`，Java 完成自身任务状态 |
| 指纹、配置、周期或账号日期安排不一致 | 拒绝写入，保留可诊断任务错误；不发布部分结果 |

Java 业务任务主键继续作为自动批次主键，使用已有的 `2e12` 起始范围，普通人工使用 `1e12` 起始范围。迁库不得重置这些业务序列。`AutoScheduleMapper` 与 `ManualMapper` 必须属于同一业务数据源、同一个事务管理器；这一绑定是宿主接入的必要条件。

普通槽位初始“待生产”；热点空槽初始“待定题”，保留冻结普通兜底选题，不能换题或领取生产。人工策划账号占用只查询人工任务产生的结果，自动批次不会误拦截人工策划。

## V0.1 发布前检查（历史记录）

以下待办已在 2026-11-03 的[双库迁移与验收](双库业务迁移与验收_2026-11-03.md)继续完成：Java 配置下发、真实双库验收、热点/营销业务迁移及旧历史退出。下文保留本阶段的原始验证范围。

1. 算法库执行 `python -m app.init_pipeline_db`（工作目录 `python-backend`），创建 `godp_algorithm_proposal` 并补齐 `commit_owner`。新增表、字段均有中文注释；迁移默认不会改变旧任务归属。
2. 业务库先发布已有的 `V3__result_slot_identity.sql`；自动任务表尚不存在时执行完整 `db/auto-planning-business.sql`，已存在时发布 `V4__auto_result_receipt.sql`。V4 为一次性升级脚本，不能重复执行。
3. Java 业务配置与 Python 准备阶段冻结的五项业务字段必须一致。当前不一致会明确拒绝提案，Java 配置自动下发到准备阶段仍待后续整合。
4. 完成目标环境数据库、内网 HTTP、调度与失败恢复验收后再开 `planning.auto-schedule.enabled`，并协调 `AUTO_SCHEDULE_OWNER=java`。本轮未执行远端 DDL、未重启或开启调度。

当前交接只覆盖 `ordinary_only` 自动策划及热点空槽；热点 T-1 的实际补题、营销内容引用、综合配置一次保存和旧历史退出仍是后续业务迁移工作。本轮不把这些能力标记为完成。

## 验证范围

Java 使用 H2 和真实 MyBatis Mapper 验证并发提交、事务回滚、指纹／日期拒绝、确认响应丢失后恢复，以及现有结果查询与人工策划回归；HTTP 客户端使用模拟服务检查鉴权与确认请求。Python 使用隔离数据库替身验证提案冻结复用、确认幂等、冲突凭证拒绝、只写算法表及 Java 归属任务停止旧提交。真实 MySQL 双库联调尚未执行。

本轮相关 Python 测试 72 项通过；Java 全量 42 项，0 失败、1 跳过。
