-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
-- 仅适用于已完成V8且尚无V9字段的库；新库不要执行。
-- DBA发布：适用于已完成V8的业务库；应用无须DDL权限。
-- 停止业务调度后检查两列尚不存在，再执行一次；新库使用完整建表DDL。
ALTER TABLE godp_planning_batch
  ADD COLUMN write_state VARCHAR(16) NOT NULL DEFAULT 'ready'
    COMMENT '结果发布状态：staging分批写入不可见、ready完整发布',
  ADD COLUMN write_cursor INT NOT NULL DEFAULT 0
    COMMENT '自动结果已提交的明细游标，分批恢复使用';
-- 随后部署无视图查询版本应用。历史批次默认ready，不改业务数据。
