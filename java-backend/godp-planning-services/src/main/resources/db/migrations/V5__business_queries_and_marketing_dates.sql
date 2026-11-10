-- 存量业务库一次性升级；本地发布工具按列和索引存在性检查后执行，重复发布请使用发布工具。
-- 新库使用 manual-business.sql、business-planning-config.sql、slot-completion.sql。
ALTER TABLE godp_planning_batch
 ADD COLUMN week_start VARCHAR(10) NULL COMMENT '批次所属自然周周一，用于时间列表数据库分页';
ALTER TABLE godp_planning_item
 ADD COLUMN publish_week VARCHAR(10) NULL COMMENT '投放日期所属自然周周一，用于账号日历数据库分页',
 MODIFY COLUMN content_status VARCHAR(16) NOT NULL DEFAULT 'planned'
 COMMENT '内容状态unassigned待定题 awaiting_market待营销引用 planned待生产 ready生产中 generated已完成 failed生产失败';
ALTER TABLE godp_manual_marketing_task
 ADD COLUMN batch_id BIGINT NULL COMMENT '已引用过审营销内容的正式策划批次编号',
 ADD COLUMN linked_count INT NOT NULL DEFAULT 0 COMMENT '已引用过审营销内容并确定投放日期的数量';
UPDATE godp_planning_batch SET week_start=DATE_FORMAT(
 DATE_SUB(STR_TO_DATE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.cycle_start')),'%Y-%m-%d'),
 INTERVAL WEEKDAY(STR_TO_DATE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.cycle_start')),'%Y-%m-%d')) DAY),'%Y-%m-%d')
 WHERE week_start IS NULL;
UPDATE godp_planning_item SET publish_week=DATE_FORMAT(
 DATE_SUB(STR_TO_DATE(publish_date,'%Y-%m-%d'),INTERVAL WEEKDAY(STR_TO_DATE(publish_date,'%Y-%m-%d')) DAY),'%Y-%m-%d')
 WHERE publish_week IS NULL;
ALTER TABLE godp_planning_batch ADD INDEX idx_batch_week(week_start,id);
ALTER TABLE godp_planning_item ADD INDEX idx_item_week_account(publish_week,account_id,id);
