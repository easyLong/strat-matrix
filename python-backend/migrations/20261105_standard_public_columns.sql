-- 六公共字段规范升级；仅适用于未执行本轮升级的原基线表。
-- 已升级或中断后恢复请使用 python-backend/tools/migrate_table_audit.py 的元数据检查入口。
-- 执行前停止任务、备份数据；MySQL DDL自动提交，不能依赖事务回滚。
-- 新库直接使用完整建表脚本，不执行此增量脚本。
SET @audit_previous_time_zone=@@session.time_zone;
SET time_zone='+00:00';

-- godp_account_mapping_rule
ALTER TABLE `godp_account_mapping_rule` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_account_mapping_rule` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_account_mapping_rule` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_account_mapping_rule` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_account_mapping_rule` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_account_profile
ALTER TABLE `godp_account_profile` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_account_profile` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_account_profile` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_account_profile` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_account_profile` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_ai_preparation
ALTER TABLE `godp_ai_preparation` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_ai_preparation` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_ai_preparation` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_ai_preparation` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_ai_preparation` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_ai_preparation_account
ALTER TABLE `godp_ai_preparation_account` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_ai_preparation_account` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_ai_preparation_account` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_ai_preparation_account` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_ai_preparation_account` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_ai_preparation_progress
ALTER TABLE `godp_ai_preparation_progress` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_ai_preparation_progress (`preparation_id`);
ALTER TABLE `godp_ai_preparation_progress` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_ai_preparation_progress` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_ai_preparation_progress` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_ai_preparation_progress` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_ai_preparation_progress` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_ai_preparation_progress` SET `created_by`='system',`updated_by`='system',`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_ai_preparation_topic
ALTER TABLE `godp_ai_preparation_topic` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_ai_preparation_topic` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_ai_preparation_topic` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_ai_preparation_topic` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_ai_preparation_topic` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_algorithm_config_command
ALTER TABLE `godp_algorithm_config_command` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_algorithm_config_command (`command_id`);
ALTER TABLE `godp_algorithm_config_command` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_algorithm_config_command` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_algorithm_config_command` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_algorithm_config_command` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_algorithm_config_command` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_algorithm_config_command` SET `created_by`='system',`updated_by`='system',`created_time`=COALESCE(`created_at`,created_time),`updated_time`=COALESCE(`created_at`,created_time);

-- godp_algorithm_proposal
ALTER TABLE `godp_algorithm_proposal` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_algorithm_proposal (`pipeline_id`);
ALTER TABLE `godp_algorithm_proposal` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_algorithm_proposal` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_algorithm_proposal` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_algorithm_proposal` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_algorithm_proposal` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_algorithm_proposal` SET `created_by`='system',`updated_by`='system',`created_time`=COALESCE(`created_at`,created_time),`updated_time`=COALESCE(`created_at`,created_time);

-- godp_manual_compute
ALTER TABLE `godp_manual_compute` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_manual_compute (`request_id`);
ALTER TABLE `godp_manual_compute` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_manual_compute` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_manual_compute` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_manual_compute` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_manual_compute` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_manual_compute` SET `created_by`='system',`updated_by`='system',`created_time`=COALESCE(`created_at`,created_time),`updated_time`=COALESCE(`updated_at`,created_time),`updated_at`=`updated_at`;

-- godp_matching_ai_cache
ALTER TABLE `godp_matching_ai_cache` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_matching_ai_cache (`cache_key`);
ALTER TABLE `godp_matching_ai_cache` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_matching_ai_cache` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_matching_ai_cache` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_matching_ai_cache` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_matching_ai_cache` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_matching_ai_cache` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`='system',`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`create_time`,created_time);

-- godp_matching_attempt
ALTER TABLE `godp_matching_attempt` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_matching_attempt` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_matching_attempt` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_matching_attempt` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_matching_attempt` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_matching_input_snapshot
ALTER TABLE `godp_matching_input_snapshot` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_matching_input_snapshot` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_matching_input_snapshot` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_matching_input_snapshot` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_matching_input_snapshot` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_matching_policy
ALTER TABLE `godp_matching_policy` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_matching_policy` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_matching_policy` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_matching_policy` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_matching_policy` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_matching_quality_run
ALTER TABLE `godp_matching_quality_run` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_godp_matching_quality_run (`task_id`);
ALTER TABLE `godp_matching_quality_run` ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除';
ALTER TABLE `godp_matching_quality_run` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_matching_quality_run` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_matching_quality_run` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_matching_quality_run` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_matching_quality_run` SET `created_by`='system',`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_matching_task
ALTER TABLE `godp_matching_task` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_matching_task` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_matching_task` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_matching_task` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_matching_task` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_planning_pipeline_run
ALTER TABLE `godp_planning_pipeline_run` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_planning_pipeline_run` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_planning_pipeline_run` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_planning_pipeline_run` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_planning_pipeline_run` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_planning_stage_run
ALTER TABLE `godp_planning_stage_run` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_planning_stage_run` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_planning_stage_run` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_planning_stage_run` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_planning_stage_run` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_strategy_config
ALTER TABLE `godp_strategy_config` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_strategy_config` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_strategy_config` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_strategy_config` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_strategy_config` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_strategy_config_version
ALTER TABLE `godp_strategy_config_version` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_strategy_config_version` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_strategy_config_version` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_strategy_config_version` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_strategy_config_version` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_system_config
ALTER TABLE `godp_system_config` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_system_config` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_system_config` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_system_config` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_system_config` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_t6_tag
ALTER TABLE `godp_t6_tag` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_t6_tag` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_t6_tag` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_t6_tag` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_t6_tag` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_topic_label_job
ALTER TABLE `godp_topic_label_job` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_topic_label_job` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_topic_label_job` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_topic_label_job` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_topic_label_job` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_topic_profile
ALTER TABLE `godp_topic_profile` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_topic_profile` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_topic_profile` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_topic_profile` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_topic_profile` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_topic_tag
ALTER TABLE `godp_topic_tag` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_topic_tag` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_topic_tag` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_topic_tag` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_topic_tag` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

-- godp_topic_tag_history
ALTER TABLE `godp_topic_tag_history` ADD COLUMN created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人';
ALTER TABLE `godp_topic_tag_history` ADD COLUMN updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人';
ALTER TABLE `godp_topic_tag_history` ADD COLUMN created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间';
ALTER TABLE `godp_topic_tag_history` ADD COLUMN updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间';
UPDATE `godp_topic_tag_history` SET `created_by`=COALESCE(NULLIF(`create_by`,''),'system'),`updated_by`=COALESCE(NULLIF(`update_by`,''),'system'),`created_time`=COALESCE(`create_time`,created_time),`updated_time`=COALESCE(`update_time`,created_time),`update_time`=`update_time`;

SET time_zone=@audit_previous_time_zone;
