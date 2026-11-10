-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
-- 仅在01-precheck的blocking_batches为0后，由DBA确认备份及目标版本。
-- 本版本不改变表结构；保留全部业务数据，不自动创建或删除数据库对象。
-- 只能回退至已验收的无视图兼容应用。依赖视图的V8/V9旧应用不可直接回退。
SELECT COUNT(*) AS blocking_batches FROM godp_planning_batch WHERE write_state<>'ready';
