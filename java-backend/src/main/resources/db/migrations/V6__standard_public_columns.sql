-- 六公共字段规范升级；仅适用于未执行本轮升级的原基线表。
-- 已升级或中断后恢复请使用 python-backend/tools/migrate_table_audit.py 的元数据检查入口。
-- 执行前停止任务、备份数据；MySQL DDL自动提交，不能依赖事务回滚。
-- 新库直接使用完整建表脚本，不执行此增量脚本。
SET @audit_previous_time_zone=@@session.time_zone;
SET time_zone='+00:00';

-- godp_auto_planning_task
ALTER TABLE `godp_auto_planning_task` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_auto_planning_task` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_auto_planning_task` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_auto_planning_task` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_auto_planning_task` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_auto_planning_task` SET `created_by`='system',`updated_by`='system',`created_time`=COALESCE(FROM_UNIXTIME(`created_at` / 1000),created_time),`updated_time`=COALESCE(FROM_UNIXTIME(`updated_at` / 1000),created_time);

-- godp_business_planning_config
ALTER TABLE `godp_business_planning_config` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_business_planning_config (`config_key`);
ALTER TABLE `godp_business_planning_config` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_business_planning_config` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_business_planning_config` MODIFY COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_business_planning_config` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_business_planning_config` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_business_planning_config` SET `created_by`='system',`created_time`=created_time,`updated_time`=COALESCE(`updated_at`,created_time);

-- godp_business_planning_config_version
ALTER TABLE `godp_business_planning_config_version` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_business_planning_config_version` MODIFY COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_business_planning_config_version` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_business_planning_config_version` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_business_planning_config_version` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_business_planning_config_version` SET `updated_by`=COALESCE(NULLIF(created_by,''),'system'),`created_time`=COALESCE(`created_at`,created_time),`updated_time`=COALESCE(`created_at`,created_time);

-- godp_manual_marketing_task
ALTER TABLE `godp_manual_marketing_task` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_manual_marketing_task` MODIFY COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_manual_marketing_task` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_manual_marketing_task` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_manual_marketing_task` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_manual_marketing_task` SET `updated_by`=COALESCE(NULLIF(created_by,''),'system'),`created_time`=COALESCE(FROM_UNIXTIME(`created_at` / 1000),created_time),`updated_time`=COALESCE(FROM_UNIXTIME(`updated_at` / 1000),created_time);

-- godp_manual_preview
ALTER TABLE `godp_manual_preview` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_manual_preview (`preview_code`);
ALTER TABLE `godp_manual_preview` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_manual_preview` MODIFY COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_manual_preview` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_manual_preview` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_manual_preview` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_manual_preview` SET `updated_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.updated_by')),'null'),'') END,NULLIF(created_by,''),'system'),`created_time`=COALESCE(FROM_UNIXTIME(`created_at` / 1000),created_time),`updated_time`=COALESCE(FROM_UNIXTIME(`created_at` / 1000),created_time);

-- godp_manual_reservation
ALTER TABLE `godp_manual_reservation` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_manual_reservation (`publish_date`,`account_id`);
ALTER TABLE `godp_manual_reservation` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_manual_reservation` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_manual_reservation` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_manual_reservation` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_manual_reservation` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_manual_reservation` SET `created_by`='system',`updated_by`='system',`created_time`=created_time,`updated_time`=created_time;

-- godp_manual_task
ALTER TABLE `godp_manual_task` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_manual_task` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_manual_task` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_manual_task` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_manual_task` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_manual_task` SET `created_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.created_by')),'null'),'') END,'system'),`updated_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.updated_by')),'null'),'') END,'system'),`created_time`=COALESCE(FROM_UNIXTIME(`created_at` / 1000),created_time),`updated_time`=COALESCE(FROM_UNIXTIME(`updated_at` / 1000),created_time);

-- godp_planning_adjustment
ALTER TABLE `godp_planning_adjustment` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_planning_adjustment` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_planning_adjustment` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_planning_adjustment` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_planning_adjustment` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_planning_adjustment` SET `created_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.created_by')),'null'),'') END,'system'),`updated_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.updated_by')),'null'),'') END,'system'),`created_time`=created_time,`updated_time`=created_time;

-- godp_planning_batch
ALTER TABLE `godp_planning_batch` MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID';
ALTER TABLE `godp_planning_batch` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_planning_batch` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_planning_batch` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_planning_batch` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_planning_batch` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_planning_batch` SET `created_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.created_by')),'null'),'') END,'system'),`updated_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.updated_by')),'null'),'') END,'system'),`created_time`=COALESCE(FROM_UNIXTIME(`created_at` / 1000),created_time),`updated_time`=COALESCE(FROM_UNIXTIME(`created_at` / 1000),created_time);

-- godp_planning_config_release
ALTER TABLE `godp_planning_config_release` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_planning_config_release (`command_id`);
ALTER TABLE `godp_planning_config_release` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_planning_config_release` MODIFY COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_planning_config_release` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_planning_config_release` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_planning_config_release` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_planning_config_release` SET `updated_by`=COALESCE(NULLIF(created_by,''),'system'),`created_time`=COALESCE(CAST(REPLACE(LEFT(`created_at`,19),'T',' ') AS DATETIME),created_time),`updated_time`=COALESCE(CAST(REPLACE(LEFT(`created_at`,19),'T',' ') AS DATETIME),created_time);

-- godp_planning_failure
ALTER TABLE `godp_planning_failure` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_planning_failure (`batch_id`,`account_key`);
ALTER TABLE `godp_planning_failure` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_planning_failure` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_planning_failure` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_planning_failure` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_planning_failure` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_planning_failure` SET `created_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.created_by')),'null'),'') END,'system'),`updated_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.updated_by')),'null'),'') END,'system'),`created_time`=created_time,`updated_time`=created_time;

-- godp_planning_item
ALTER TABLE `godp_planning_item` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_planning_item` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_planning_item` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_planning_item` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_planning_item` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_planning_item` SET `created_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.created_by')),'null'),'') END,'system'),`updated_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.updated_by')),'null'),'') END,'system'),`created_time`=created_time,`updated_time`=created_time;

-- godp_planning_resource_claim
ALTER TABLE `godp_planning_resource_claim` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_planning_resource_claim (`resource_kind`,`resource_key`);
ALTER TABLE `godp_planning_resource_claim` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_planning_resource_claim` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_planning_resource_claim` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_planning_resource_claim` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_planning_resource_claim` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_planning_resource_claim` SET `created_by`='system',`updated_by`='system',`created_time`=COALESCE(`created_at`,created_time),`updated_time`=COALESCE(`created_at`,created_time);

-- godp_planning_task_archive
ALTER TABLE `godp_planning_task_archive` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_planning_task_archive (`archive_key`);
ALTER TABLE `godp_planning_task_archive` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_planning_task_archive` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_planning_task_archive` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_planning_task_archive` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_planning_task_archive` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_planning_task_archive` SET `created_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.created_by')),'null'),'') END,'system'),`updated_by`=COALESCE(CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.updated_by')),'null'),'') END,'system'),`created_time`=COALESCE(FROM_UNIXTIME(`created_at` / 1000),created_time),`updated_time`=COALESCE(FROM_UNIXTIME(`created_at` / 1000),created_time);

-- Business-owned JSON snapshots projected for SQL filtering, aggregation and pagination.
CREATE OR REPLACE VIEW godp_planning_item_read AS
SELECT i.id,i.batch_id,i.slot_id,i.account_id,i.publish_date,i.publish_week,i.payload,i.content_status,i.version,
 b.created_at AS sort_millis,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(b.payload,'$.runtime_active')),'null'),'true') AS runtime_active,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.plan_type')),'null'),'manual') AS plan_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.cycle_start')),'null'),i.publish_date) AS cycle_start,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.cycle_end')),'null'),i.publish_date) AS cycle_end,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.topic_id')),'null'),'') AS topic_id,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.topic_type')),'null'),'') AS topic_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.content_type')),'null'),'') AS content_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.slot_type')),'null'),'') AS slot_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.content_role')),'null'),'') AS content_role,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_name')),'null'),'') AS account_name,
 COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.um_no')),'null'),''),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.source_payload.um_no')),'null'),'') AS owner_um,
 COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.organization')),'null'),''),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.source_payload.organization')),'null'),'') AS organization,
 COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.platform')),'null'),''),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.source_payload.platform')),'null'),'') AS platform,
 COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.account_type')),'null'),''),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.source_payload.account_type')),'null'),'') AS account_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.lifecycle_stage')),'null'),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.lifecycle_stage')),'null'),'') AS lifecycle_stage,
 CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.followers')),'null'),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.followers_count')),'null'),'0') AS SIGNED) AS followers
FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id
WHERE i.del_flag='N' AND b.del_flag='N';

CREATE OR REPLACE VIEW godp_planning_batch_read AS
SELECT id,payload,created_at,week_start,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.plan_type')),'null'),'manual') AS plan_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.cycle_start')),'null'),'') AS cycle_start,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.cycle_end')),'null'),'') AS cycle_end,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.batch_code')),'null'),'') AS batch_code,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.task_name')),'null'),'') AS task_name,
 CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.account_count')),'null'),'0') AS SIGNED) AS account_count,
 CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.completed_count')),'null'),'0') AS SIGNED) AS completed_count,
 CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.failed_count')),'null'),'0') AS SIGNED) AS failed_count,
 CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.topic_count')),'null'),'0') AS SIGNED) AS topic_count
FROM godp_planning_batch WHERE del_flag='N';

CREATE OR REPLACE VIEW godp_planning_task_read AS
SELECT CONCAT('manual:',t.id) AS row_key,t.id,'manual' AS kind,t.payload,t.created_at,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(t.payload,'$.task_name')),'') AS task_name,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(b.payload,'$.batch_code')),'') AS batch_code,
 JSON_UNQUOTE(JSON_EXTRACT(t.payload,'$.publish_date')) AS publish_date,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(t.payload,'$.created_by')),'') AS created_by,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(b.payload,'$.content_status')),'待生产') AS content_status
FROM godp_manual_task t LEFT JOIN godp_planning_batch b ON b.id=t.id AND b.del_flag='N'
WHERE t.del_flag='N'
UNION ALL
SELECT CONCAT('marketing:',id),id,'marketing',topic_snapshot_json,created_at,task_name,task_code,NULL,created_by,status
FROM godp_manual_marketing_task WHERE del_flag='N'
UNION ALL
SELECT archive_key,source_id,'archive',payload,created_at,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.task_name')),''),
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.batch_code')),''),
 NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.publish_date')),'null'),
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.created_by')),''),
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.content_status')),'待生产')
FROM godp_planning_task_archive WHERE del_flag='N';

SET time_zone=@audit_previous_time_zone;
