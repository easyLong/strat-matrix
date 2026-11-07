-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
-- 兼容回退前停止调度/写入；blocking_batches必须为0，否则先用新版继续推进至完整发布。
-- 检查SQL不会自动中止后续脚本，由DBA审核结果并签认后才可继续。
SELECT COUNT(*) AS blocking_batches FROM godp_planning_batch WHERE write_state<>'ready';
SELECT id,write_state,write_cursor FROM godp_planning_batch WHERE write_state<>'ready';
SELECT status,COUNT(*) AS task_count FROM godp_auto_planning_task WHERE del_flag='N' GROUP BY status;
