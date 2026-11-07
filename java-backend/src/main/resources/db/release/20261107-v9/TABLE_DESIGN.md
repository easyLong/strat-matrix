# Java业务表与索引评审清单

生成自当前DDL；仅包含本模块14张业务表，不包含Python算法表和行内内容流水表。

所有表采用InnoDB/utf8mb4；排序规则尚未固定，需按目标schema现有规范确认后发布。

现有id均为BIGINT自增；业务编号/槽位编号另设唯一约束，保留现有业务ID范围。

| 表名 | 唯一约束与索引 |
| --- | --- |
| `godp_auto_planning_task` | UNIQUE KEY uq_auto_planning_cycle(cycle_start)<br>KEY idx_auto_planning_status(status, updated_at) |
| `godp_business_planning_config` | UNIQUE KEY uk_audit_legacy_godp_business_planning_config (config_key) |
| `godp_business_planning_config_version` | UNIQUE KEY uq_business_config_version(config_key, version) |
| `godp_manual_marketing_task` | KEY idx_marketing_created(created_at,id)<br>KEY idx_marketing_status(status,id)<br>task_code VARCHAR(64) NOT NULL UNIQUE COMMENT '人工营销策划任务编号'<br>request_id VARCHAR(64) NOT NULL UNIQUE COMMENT '前端提交幂等编号' |
| `godp_manual_preview` | UNIQUE KEY uk_audit_legacy_godp_manual_preview (preview_code) |
| `godp_manual_reservation` | UNIQUE KEY uk_audit_legacy_godp_manual_reservation (publish_date,account_id) |
| `godp_manual_task` | KEY idx_task_status(status)<br>preview_code VARCHAR(64) NOT NULL UNIQUE COMMENT '预览编号，防重复提交'<br>task_code VARCHAR(64) NOT NULL UNIQUE COMMENT '业务及计算幂等编号' |
| `godp_planning_adjustment` |  |
| `godp_planning_batch` |  |
| `godp_planning_config_release` | KEY idx_config_release_state(status,version)<br>UNIQUE KEY uk_audit_legacy_godp_planning_config_release (command_id)<br>active_version INT NULL UNIQUE COMMENT '待发布或已发布版本占用，拒绝后释放' |
| `godp_planning_failure` | UNIQUE KEY uk_audit_legacy_godp_planning_failure (batch_id,account_key) |
| `godp_planning_item` | UNIQUE KEY uq_batch_slot(batch_id,slot_id)<br>KEY idx_result_account_date(account_id,publish_date)<br>KEY idx_result_batch_date(batch_id,publish_date)<br>KEY idx_result_content_flow_scan(content_status,id) |
| `godp_planning_resource_claim` | KEY idx_resource_item(item_id)<br>UNIQUE KEY uk_audit_legacy_godp_planning_resource_claim (resource_kind,resource_key) |
| `godp_planning_task_archive` | UNIQUE KEY uk_audit_legacy_godp_planning_task_archive (archive_key) |

## 业务动作与防重复边界

| 动作 | 数据库与服务共同约束 |
| --- | --- |
| 周自动策划 | cycle_start唯一；锁定同一自动任务；恢复时校验proposal_hash |
| 正式明细 | (batch_id,slot_id)唯一；每页明细与游标同事务提交 |
| 人工提交 | preview_code/task_code唯一；营销request_id唯一并核对request_hash |
| 账号日期占用 | (publish_date,account_id)唯一；释放后原行逻辑复用 |
| 热点/过审内容引用 | (resource_kind,resource_key)唯一；重复占用拒绝 |
| 配置发布 | command_id唯一、版本校验；配置历史(config_key,version)唯一 |
| 内容流水 | 行内目标实现提供planningItemId唯一、版本单调及原始回执；本模块不替目标建表 |

容量评估：自动明细约为账号数×每周策划日数×保留周数，另加人工明细；账号/选题快照LONGTEXT需按真实平均字节和索引占用估算。归档保留期、分区需求由DBA和业务方确认。

高频JSON筛选、模糊名称查询可能无法利用普通索引；现场EXPLAIN及规模压测后决定结构化投影，不能凭样例判断性能已达标。

自动结果：每次推进最多写500条明细，事务还包含少量游标/状态记录；若宿主将500定义为所有DML影响行数上限，应进一步下调明细批量。

人工结果仍按单任务原子写入，规模化分批是后续专项；本轮未声称全部写入路径均已拆分。
