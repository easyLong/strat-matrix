-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
SELECT DATABASE() AS target_schema, CURRENT_USER() AS release_user, VERSION() AS mysql_version;
SELECT TABLE_NAME,ENGINE,TABLE_COLLATION,TABLE_COMMENT FROM information_schema.TABLES
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('godp_auto_planning_task','godp_business_planning_config','godp_business_planning_config_version','godp_manual_marketing_task','godp_manual_preview','godp_manual_reservation','godp_manual_task','godp_planning_adjustment','godp_planning_batch','godp_planning_config_release','godp_planning_failure','godp_planning_item','godp_planning_resource_claim','godp_planning_task_archive') ORDER BY TABLE_NAME;

-- existing_tables必须为14，public_columns必须为84，v9_columns必须为0。
SELECT COUNT(*) AS existing_tables FROM information_schema.TABLES
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('godp_auto_planning_task','godp_business_planning_config','godp_business_planning_config_version','godp_manual_marketing_task','godp_manual_preview','godp_manual_reservation','godp_manual_task','godp_planning_adjustment','godp_planning_batch','godp_planning_config_release','godp_planning_failure','godp_planning_item','godp_planning_resource_claim','godp_planning_task_archive');
SELECT COUNT(*) AS public_columns FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('godp_auto_planning_task','godp_business_planning_config','godp_business_planning_config_version','godp_manual_marketing_task','godp_manual_preview','godp_manual_reservation','godp_manual_task','godp_planning_adjustment','godp_planning_batch','godp_planning_config_release','godp_planning_failure','godp_planning_item','godp_planning_resource_claim','godp_planning_task_archive')
 AND COLUMN_NAME IN ('id','del_flag','created_by','updated_by','created_time','updated_time');
SELECT COUNT(*) AS v9_columns FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='godp_planning_batch'
 AND COLUMN_NAME IN ('write_state','write_cursor');
-- 以下V7/V8基线结果分别必须为2、1；少任一项不得跳版本。
SELECT COUNT(*) AS v7_columns FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
 AND TABLE_NAME IN ('godp_business_planning_config','godp_business_planning_config_version')
 AND COLUMN_NAME='content_production_lead_days_json';
SELECT COUNT(DISTINCT INDEX_NAME) AS v8_indexes FROM information_schema.STATISTICS
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='godp_planning_item' AND INDEX_NAME='idx_result_content_flow_scan';
-- 查看已有自动任务，停止调度并确认没有执行中的写入后再发布。
SELECT status,COUNT(*) AS task_count FROM godp_auto_planning_task WHERE del_flag='N' GROUP BY status;
