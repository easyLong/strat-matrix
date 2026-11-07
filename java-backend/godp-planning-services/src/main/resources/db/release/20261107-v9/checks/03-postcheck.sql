-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
SELECT DATABASE() AS target_schema, CURRENT_USER() AS release_user, VERSION() AS mysql_version;
SELECT TABLE_NAME,ENGINE,TABLE_COLLATION,TABLE_COMMENT FROM information_schema.TABLES
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('godp_auto_planning_task','godp_business_planning_config','godp_business_planning_config_version','godp_manual_marketing_task','godp_manual_preview','godp_manual_reservation','godp_manual_task','godp_planning_adjustment','godp_planning_batch','godp_planning_config_release','godp_planning_failure','godp_planning_item','godp_planning_resource_claim','godp_planning_task_archive') ORDER BY TABLE_NAME;

-- 三个视图必须全部存在，新增字段类型、默认值、中文说明需与DDL一致。
SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,COLUMN_COMMENT
 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
 AND TABLE_NAME='godp_planning_batch' AND COLUMN_NAME IN ('write_state','write_cursor');
SELECT TABLE_NAME,VIEW_DEFINITION FROM information_schema.VIEWS WHERE TABLE_SCHEMA=DATABASE()
 AND TABLE_NAME IN ('godp_planning_item_read','godp_planning_batch_read','godp_planning_task_read');
SELECT write_state,COUNT(*) AS batch_count FROM godp_planning_batch GROUP BY write_state;
SELECT COUNT(*) AS invalid_write_states FROM godp_planning_batch
 WHERE write_state NOT IN ('ready','staging') OR write_cursor<0;
SELECT COUNT(*) AS leaked_staging_items FROM godp_planning_item_read i
 JOIN godp_planning_batch b ON b.id=i.batch_id WHERE b.write_state<>'ready';
-- 应用账号应独立验证：具有必要DML和视图SELECT，无需CREATE/ALTER/DROP。
SHOW GRANTS;
