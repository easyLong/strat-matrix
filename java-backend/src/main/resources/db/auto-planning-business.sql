CREATE TABLE IF NOT EXISTS godp_auto_planning_task (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '自动周策划业务任务主键',
 cycle_start DATE NOT NULL COMMENT '目标策划周期开始日期，周一',
 cycle_end DATE NOT NULL COMMENT '目标策划周期结束日期，周日',
 business_config_version INT NOT NULL COMMENT '触发时采用的Java业务配置版本',
 business_config_json LONGTEXT NOT NULL COMMENT '触发时冻结的Java业务配置完整快照',
 status VARCHAR(24) NOT NULL COMMENT '任务状态，待发起、计算中、待确认、已完成、策划失败或旧结果已存在',
 pipeline_id BIGINT NULL COMMENT 'Python算法Pipeline运行编号',
 legacy_batch_id BIGINT NULL COMMENT '过渡期Python旧正式批次编号',
 business_batch_id BIGINT NULL COMMENT 'Java业务库已提交的正式批次编号',
 proposal_hash CHAR(64) NULL COMMENT '已提交算法提案的SHA256指纹，用于重复确认',
 confirmation_attempts INT NOT NULL DEFAULT 0 COMMENT '落库后的Python确认请求尝试次数',
 attempts INT NOT NULL DEFAULT 0 COMMENT '发起算法请求的尝试次数',
 last_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '最近一次发起失败摘要',
 created_at BIGINT NOT NULL COMMENT '任务创建时间毫秒戳',
 updated_at BIGINT NOT NULL COMMENT '任务更新时间毫秒戳',
 UNIQUE KEY uq_auto_planning_cycle(cycle_start),
 KEY idx_auto_planning_status(status, updated_at)
) ENGINE=InnoDB AUTO_INCREMENT=2000000000000 DEFAULT CHARSET=utf8mb4 COMMENT='Java自动周策划触发任务';
