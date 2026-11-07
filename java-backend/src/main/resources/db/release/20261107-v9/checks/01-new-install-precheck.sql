-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
SELECT DATABASE() AS target_schema, CURRENT_USER() AS release_user, VERSION() AS mysql_version;
SELECT TABLE_NAME,ENGINE,TABLE_COLLATION,TABLE_COMMENT FROM information_schema.TABLES
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('godp_auto_planning_task','godp_business_planning_config','godp_business_planning_config_version','godp_manual_marketing_task','godp_manual_preview','godp_manual_reservation','godp_manual_task','godp_planning_adjustment','godp_planning_batch','godp_planning_config_release','godp_planning_failure','godp_planning_item','godp_planning_resource_claim','godp_planning_task_archive') ORDER BY TABLE_NAME;

-- existing_tables必须为0；不满足则停止，改用匹配基线的升级包。
SELECT COUNT(*) AS existing_tables FROM information_schema.TABLES
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('godp_auto_planning_task','godp_business_planning_config','godp_business_planning_config_version','godp_manual_marketing_task','godp_manual_preview','godp_manual_reservation','godp_manual_task','godp_planning_adjustment','godp_planning_batch','godp_planning_config_release','godp_planning_failure','godp_planning_item','godp_planning_resource_claim','godp_planning_task_archive');
