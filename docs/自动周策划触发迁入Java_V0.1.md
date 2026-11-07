# 自动周策划触发迁入 Java V0.1

2026-11-03 更新：本文件保留首轮触发迁移记录。普通自动策划的 Java 正式提交与 Python 确认现已完成代码和隔离测试，当前链路、状态和发布步骤见[正式提交与确认](自动策划Java正式提交与确认_V0.1.md)。以下“当前／仍需”描述对应 2026-11-02 的首轮状态。

日期：2026-11-02。本轮只迁移**发起时机和业务任务受理**；Python 仍执行 V2 算法 Pipeline，并在现有过渡路径写正式结果。不能据此宣布自动策划业务迁移完成。

## 当前调用

1. 宿主调度器调用 Java `AutoScheduleService.tick(Instant.now())`。行外 `LocalJobPulse` 仅模拟宿主调度。
2. Java 从业务库当前配置读取调度星期和时刻，以 `Asia/Shanghai` 判定是否应为下周一至周日发起任务。
3. 到期后在业务库 `godp_auto_planning_task` 按周期创建唯一任务，同时冻结当时的业务配置版本和完整快照；已受理的周期不重复发起，失败的“待发起”任务可由下一次调度重试。
4. Java 通过 `AutoSchedulePort` 请求受保护的 `POST /api/internal/auto-planning/start`；Python 从算法库选择已批准的 V2 策略与账号范围，返回 Pipeline 编号或过渡期已有批次编号。
5. Java 记录算法受理结果。后续调度先调用 `advanceOpen` 继续旧任务，再调用 `tick` 判断本次新周期；即使业务配置后来改变了调度日，已受理任务也能继续对账。Java 读取 Pipeline 状态后将任务更新为“已完成”或“策划失败”，完成时保留过渡期 Python 正式批次编号。首次“计算中”仅表示**开始计算**，不代表策划完成。

## 驻场替换与开关

- 业务表：`java-backend/godp-planning-services/src/main/resources/db/auto-planning-business.sql`，所有字段含中文注释，由行内数据库发布流程执行；Java 通过 `AutoScheduleMapper` 访问。
- 业务配置：先将四项业务配置迁入 Java 业务库，并确认与当前 Python 算法配置一致，再启用 `planning.auto-schedule.enabled=true`。
- Java 算法端口：宿主实现或绑定 `AutoSchedulePort`；行外 `AutoSchedulePythonClient` 仅提供内网 HTTP 参考。
- 在算法库初始化 `godp_system_config.AUTO_SCHEDULE_OWNER` 后置为 `java`，旧 Python 周调度改为只返回 `delegated_to_java`。升级代码但尚未新增该配置行时保持旧 Python 调度；数据库读取失败仍报错。需要与 Java 开关同一发布窗口切换，避免重复发起或漏发。
- 宿主调度器负责周期性依次调用 `advanceOpen`、`tick`；不要复制行外的 `LocalJobPulse` 或 Python 常驻 `ordinary_scheduler.serve()`。

## 仍需完成的业务迁移

已新增只读的算法提案交接契约，Java 可以携带冻结业务配置版本读取 Python 验证后的槽位提案；具体范围及尚未完成的正式提交步骤见[自动策划算法提案交接 V0.1](自动策划算法提案交接_V0.1.md)。该接口不改变当前任务状态，也不写正式结果。

Python Pipeline 的结果提交仍写 Python 库的正式批次、明细和热点槽位。下一步需由 Java 校验并提交算法提案到业务库，再将 Python `result_commit` 改为只记录算法计算结果和 Java 受理凭证。此后才迁热点 T-1、营销内容引用、内容状态与统一结果查询。当前 Java 与 Python 分库存储的业务配置还没有冻结传递契约，因此本轮**默认不启用 Java 周调度**。

本地配置指向的 `strat_matrix_bus` 已只读核查：`godp_auto_planning_task` 与 `godp_manual_marketing_task` 尚未发布，旧 `godp_planning_item` 也尚无 `slot_id`。运行服务仍使用旧版本；本轮没有在运行中的远端库执行 DDL 或切换服务。
