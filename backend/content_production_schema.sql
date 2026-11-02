
CREATE TABLE IF NOT EXISTS godp_topic_usage_fact (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '选题内容生产使用事实主键ID',
    production_task_id VARCHAR(64) NOT NULL COMMENT '首次生产成功的任务唯一编码，重复回调不重复计数',
    slot_id VARCHAR(64) NOT NULL COMMENT '成功生产对应的策划槽位编码',
    result_version INT NOT NULL COMMENT '成功生产对应的策划结果版本',
    topic_id VARCHAR(64) NOT NULL COMMENT '本次成功使用的选题编码',
    topic_type VARCHAR(16) NOT NULL COMMENT '成功使用的选题来源类型：普通、营销或热点',
    content_id VARCHAR(64) NULL COMMENT '内容方返回的内容编码，可为空',
    occurred_at DATETIME(6) NOT NULL COMMENT '首次确认生产成功时间，按UTC保存',
    create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'production-callback' COMMENT '创建来源',
    update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'production-callback' COMMENT '最后修改来源',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志，N有效',
    UNIQUE KEY uk_topic_usage_task (production_task_id),
    UNIQUE KEY uk_topic_usage_slot_version (slot_id,result_version),
    KEY idx_topic_usage_topic (topic_type,topic_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='以槽位版本首次内容生产成功为口径的选题使用事实';
