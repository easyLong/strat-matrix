-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
-- 仅用于全新库；先检查14张业务表均不存在。不得用IF NOT EXISTS替代存量升级。
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

CREATE TABLE IF NOT EXISTS godp_business_planning_config (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    config_key VARCHAR(32) NOT NULL COMMENT '配置键，当前固定为operations',
    version INT NOT NULL COMMENT '当前业务配置版本号',
    planning_days VARCHAR(32) NOT NULL COMMENT '每周策划日，逗号分隔的星期数字1至7',
    schedule_day TINYINT NOT NULL COMMENT '自动策划调度星期，1为周一',
    schedule_time CHAR(5) NOT NULL COMMENT '自动策划调度时间，24小时制HH:mm',
    marketing_max INT NOT NULL COMMENT '单营销账号每周营销内容上限',
    hotspot_ratio INT NOT NULL COMMENT '热点选题占比，整数百分比',
    content_production_lead_days_json VARCHAR(255) NULL COMMENT '按普通营销热点配置的内容生产提前自然日JSON，空或缺项表示未配置，0为投放当天',
    updated_at DATETIME(3) NOT NULL COMMENT '最近修改时间',
    UNIQUE KEY uk_audit_legacy_godp_business_planning_config (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI策划业务配置当前版本';

CREATE TABLE IF NOT EXISTS godp_business_planning_config_version (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    config_key VARCHAR(32) NOT NULL COMMENT '配置键，当前固定为operations',
    version INT NOT NULL COMMENT '业务配置版本号',
    planning_days VARCHAR(32) NOT NULL COMMENT '该版本每周策划日',
    schedule_day TINYINT NOT NULL COMMENT '该版本自动策划调度星期',
    schedule_time CHAR(5) NOT NULL COMMENT '该版本自动策划调度时间',
    marketing_max INT NOT NULL COMMENT '该版本单营销账号每周营销内容上限',
    hotspot_ratio INT NOT NULL COMMENT '该版本热点选题占比',
    content_production_lead_days_json VARCHAR(255) NULL COMMENT '该版本按选题类型配置的内容生产提前自然日JSON，空表示历史未记录',
    action VARCHAR(16) NOT NULL COMMENT '版本动作，保存或恢复',
    source_version INT NULL COMMENT '恢复动作所引用的历史版本号',
    created_at DATETIME(3) NOT NULL COMMENT '该版本创建时间',
    UNIQUE KEY uq_business_config_version(config_key, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI策划业务配置历史版本';

CREATE TABLE IF NOT EXISTS godp_planning_config_release (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    command_id VARCHAR(64) NOT NULL COMMENT '两库配置发布命令编号，重试不变',
    version INT NOT NULL COMMENT '页面综合配置版本',
    active_version INT NULL UNIQUE COMMENT '待发布或已发布版本占用，拒绝后释放',
    status VARCHAR(16) NOT NULL COMMENT '发布状态pending completed rejected',
    request_hash CHAR(64) NOT NULL COMMENT '页面提交完整配置指纹',
    config_json LONGTEXT NOT NULL COMMENT '页面综合配置快照，包含业务规则与算法参数',
    business_expected_version INT NOT NULL COMMENT '发布前业务规则版本',
    algorithm_version INT NOT NULL COMMENT '发布前或确认后的算法配置版本',
    created_at VARCHAR(40) NOT NULL COMMENT '配置提交时间UTC字符串',
    action VARCHAR(16) NOT NULL COMMENT '保存、恢复或首次迁入',
    source_version INT NULL COMMENT '恢复时引用的综合历史版本',
    last_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '配置发布失败摘要',
    KEY idx_config_release_state(status,version),
    UNIQUE KEY uk_audit_legacy_godp_planning_config_release (command_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='综合配置持久化发布命令与生效历史';

CREATE TABLE IF NOT EXISTS godp_auto_planning_task (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
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

CREATE TABLE IF NOT EXISTS godp_planning_resource_claim (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    resource_kind VARCHAR(24) NOT NULL COMMENT '资源类型hotspot热点日占用或marketing营销内容引用',
    resource_key VARCHAR(160) NOT NULL COMMENT '热点投放日与选题ID组合或营销内容ID',
    item_id BIGINT NOT NULL COMMENT '领取该资源的正式策划明细编号',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '资源绑定时间',
    KEY idx_resource_item(item_id),
    UNIQUE KEY uk_audit_legacy_godp_planning_resource_claim (resource_kind,resource_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='热点选题与过审营销内容的业务占用';

CREATE TABLE IF NOT EXISTS godp_planning_failure (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    batch_id BIGINT NOT NULL COMMENT '产生失败的策划批次编号',
    account_key VARCHAR(64) NOT NULL COMMENT '失败账号编号或批次级异常占位键',
    payload LONGTEXT NOT NULL COMMENT '账号UM号昵称失败原因等展示信息',
    UNIQUE KEY uk_audit_legacy_godp_planning_failure (batch_id,account_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策划失败账号及原因的业务记录';
