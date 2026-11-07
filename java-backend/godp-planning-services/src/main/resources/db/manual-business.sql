CREATE TABLE IF NOT EXISTS godp_manual_preview (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    preview_code VARCHAR(64) NOT NULL COMMENT 'Java预览编号',
    payload LONGTEXT NOT NULL COMMENT '业务输入及账号选题冻结快照',
    expires_at BIGINT NOT NULL COMMENT '过期时间毫秒戳',
    created_at BIGINT NOT NULL COMMENT '创建时间毫秒戳',
    UNIQUE KEY uk_audit_legacy_godp_manual_preview (preview_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Java普通人工策划预览';
CREATE TABLE IF NOT EXISTS godp_manual_task (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    preview_code VARCHAR(64) NOT NULL UNIQUE COMMENT '预览编号，防重复提交',
    task_code VARCHAR(64) NOT NULL UNIQUE COMMENT '业务及计算幂等编号',
    status VARCHAR(16) NOT NULL COMMENT '业务执行状态pending computing completed failed',
    payload LONGTEXT NOT NULL COMMENT '任务显示字段及冻结输入',
    error_message VARCHAR(500) NOT NULL DEFAULT '' COMMENT '业务失败原因',
    created_at BIGINT NOT NULL COMMENT '创建时间毫秒戳',
    updated_at BIGINT NOT NULL COMMENT '更新时间毫秒戳',
    KEY idx_task_status(status)
) ENGINE=InnoDB AUTO_INCREMENT=1000000000000 DEFAULT CHARSET=utf8mb4 COMMENT='Java普通人工策划业务任务';
CREATE TABLE IF NOT EXISTS godp_manual_marketing_task (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    task_code VARCHAR(64) NOT NULL UNIQUE COMMENT '人工营销策划任务编号',
    request_id VARCHAR(64) NOT NULL UNIQUE COMMENT '前端提交幂等编号',
    request_hash CHAR(64) NOT NULL COMMENT '任务名称选题和生成数量的请求指纹',
    task_name VARCHAR(120) NOT NULL COMMENT '策划任务名称',
    topic_id VARCHAR(64) NOT NULL COMMENT '选择的选题编号',
    allocation_count INT NOT NULL COMMENT '要求生成的营销内容数量',
    topic_snapshot_json LONGTEXT NOT NULL COMMENT '提交时的选题资料快照',
    status VARCHAR(24) NOT NULL DEFAULT '待分配' COMMENT '内容分配与生产状态',
    account_count INT NOT NULL DEFAULT 0 COMMENT '内容系统已分配的账号数量',
    content_completed_count INT NOT NULL DEFAULT 0 COMMENT '已完成的营销内容数量',
    content_failed_count INT NOT NULL DEFAULT 0 COMMENT '生成失败的营销内容数量',
    production_reported_at BIGINT NULL COMMENT '最近采纳的内容方状态时间毫秒戳',
    batch_id BIGINT NULL COMMENT '过审内容完成投放日期编排后关联的正式批次',
    linked_count INT NOT NULL DEFAULT 0 COMMENT '已引用过审内容并确定投放日期的数量',
    created_at BIGINT NOT NULL COMMENT '创建时间毫秒戳',
    updated_at BIGINT NOT NULL COMMENT '更新时间毫秒戳',
    KEY idx_marketing_created(created_at,id),
    KEY idx_marketing_status(status,id)
) ENGINE=InnoDB AUTO_INCREMENT=1000000000000 DEFAULT CHARSET=utf8mb4 COMMENT='人工营销策划业务任务';
CREATE TABLE IF NOT EXISTS godp_manual_reservation (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    publish_date VARCHAR(10) NOT NULL COMMENT '投放日期',
    account_id VARCHAR(64) NOT NULL COMMENT '账号唯一编号',
    task_id BIGINT NOT NULL COMMENT '占用该账号日期的任务编号',
    UNIQUE KEY uk_audit_legacy_godp_manual_reservation (publish_date,account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Java人工策划账号日期占用，失败释放';
CREATE TABLE IF NOT EXISTS godp_planning_batch (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    week_start VARCHAR(10) NULL COMMENT '批次所属自然周的周一，用于时间列表数据库分页',
    write_state VARCHAR(16) NOT NULL DEFAULT 'ready' COMMENT '结果发布状态：staging分批写入不可见、ready完整发布',
    write_cursor INT NOT NULL DEFAULT 0 COMMENT '自动结果已提交的明细游标，分批恢复使用',
    payload LONGTEXT NOT NULL COMMENT '正式批次基本信息快照',
    created_at BIGINT NOT NULL COMMENT '创建时间毫秒戳'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Java普通人工策划正式批次';
CREATE TABLE IF NOT EXISTS godp_planning_item (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    batch_id BIGINT NOT NULL COMMENT '所属批次',
    slot_id VARCHAR(128) NOT NULL COMMENT '批次内槽位唯一编号，同账号可有多条策划',
    account_id VARCHAR(64) NOT NULL COMMENT '所属账号',
    publish_date VARCHAR(10) NOT NULL COMMENT '投放日期',
    publish_week VARCHAR(10) NULL COMMENT '投放日期所属自然周的周一，用于账号日历数据库分页',
    payload LONGTEXT NOT NULL COMMENT '正式明细、账号及选题快照',
    content_status VARCHAR(16) NOT NULL DEFAULT 'planned' COMMENT '内容状态unassigned待定题 awaiting_market待营销引用 planned待生产 ready生产中 generated已完成 failed生产失败',
    version INT NOT NULL DEFAULT 1 COMMENT '结果乐观锁版本',
    UNIQUE KEY uq_batch_slot(batch_id,slot_id),
    KEY idx_result_account_date(account_id,publish_date),
    KEY idx_result_batch_date(batch_id,publish_date),
    KEY idx_result_content_flow_scan(content_status,id)
) ENGINE=InnoDB AUTO_INCREMENT=1000000000000 DEFAULT CHARSET=utf8mb4 COMMENT='Java普通人工策划正式明细';
CREATE TABLE IF NOT EXISTS godp_planning_adjustment (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    item_id BIGINT NOT NULL COMMENT '策划明细编号',
    payload LONGTEXT NOT NULL COMMENT '操作人、时间、调整前后选题及原因'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Java策划明细调整记录';

CREATE TABLE IF NOT EXISTS godp_planning_task_archive (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    archive_key VARCHAR(80) NOT NULL COMMENT '旧任务类型与编号组成的迁移唯一键',
    source_id BIGINT NOT NULL COMMENT '旧任务原始编号',
    payload LONGTEXT NOT NULL COMMENT '已确认的旧任务列表完整展示快照',
    created_at BIGINT NOT NULL COMMENT '旧任务创建时间毫秒戳',
    UNIQUE KEY uk_audit_legacy_godp_planning_task_archive (archive_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='历史策划任务只读归档，不参与新任务执行';
