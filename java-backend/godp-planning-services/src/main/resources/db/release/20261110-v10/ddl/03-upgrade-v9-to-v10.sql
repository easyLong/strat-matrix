-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
-- V9到V10没有新增业务表或字段，只切换应用中的MyBatis查询。
-- 先执行checks/05-upgrade-v9-precheck.sql，再部署V10应用。无需创建、重建或查询数据库视图。
-- 旧库已有的历史视图由DBA另行评估清理，本包不自动删除任何数据库对象。
SELECT DATABASE() AS target_schema;
SELECT write_state,COUNT(*) AS batch_count FROM godp_planning_batch GROUP BY write_state;
