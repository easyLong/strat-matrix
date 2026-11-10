-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
-- 只读；真实EXPLAIN和容量结论由现场实际数据验证。
SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART
 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE()
 AND TABLE_NAME IN ('godp_auto_planning_task','godp_business_planning_config','godp_business_planning_config_version','godp_manual_marketing_task','godp_manual_preview','godp_manual_reservation','godp_manual_task','godp_planning_adjustment','godp_planning_batch','godp_planning_config_release','godp_planning_failure','godp_planning_item','godp_planning_resource_claim','godp_planning_task_archive') ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX;
EXPLAIN SELECT i.id FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id
 WHERE i.del_flag='N' AND b.del_flag='N' AND b.write_state='ready'
 AND i.content_status='planned' AND i.id>0 ORDER BY i.id LIMIT 500;
EXPLAIN SELECT id FROM godp_planning_item WHERE account_id='REPLACE_WITH_SAMPLE_ACCOUNT'
 AND publish_date BETWEEN '2026-11-02' AND '2026-11-08' AND del_flag='N';
