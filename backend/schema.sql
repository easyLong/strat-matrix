-- MySQL schema. Run explicitly after confirming the target database.
-- No foreign keys, stored procedures, functions, or views.

CREATE TABLE IF NOT EXISTS godp_strategy_config (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '配置记录主键ID',
    config_key VARCHAR(64) NOT NULL COMMENT '配置项唯一标识',
    config_json LONGTEXT NOT NULL COMMENT '配置内容JSON',
    version INT NOT NULL DEFAULT 1 COMMENT '配置版本号',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_config_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='运营策划配置';

CREATE TABLE IF NOT EXISTS godp_account (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '账号记录主键ID',
    account_code VARCHAR(64) NOT NULL COMMENT '客户账号唯一编码',
    account_name VARCHAR(120) NOT NULL COMMENT '账号展示名称',
    city VARCHAR(50) NOT NULL DEFAULT '' COMMENT '账号所属城市',
    persona VARCHAR(80) NOT NULL DEFAULT '' COMMENT '账号人设类型',
    marketing_eligible TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否具备营销资格：1是0否',
    status VARCHAR(32) NOT NULL DEFAULT '启用' COMMENT '账号启用状态',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_account_code (account_code),
    KEY idx_account_city_persona (city, persona)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='账号档案';

CREATE TABLE IF NOT EXISTS godp_topic (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '选题记录主键ID',
    topic_code VARCHAR(64) NOT NULL COMMENT '客户选题唯一编码',
    title VARCHAR(255) NOT NULL COMMENT '选题标题',
    category VARCHAR(50) NOT NULL DEFAULT '' COMMENT '选题分类',
    is_marketing TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为营销选题：1是0否',
    status VARCHAR(32) NOT NULL DEFAULT '可用' COMMENT '选题启用状态',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_topic_code (topic_code),
    KEY idx_topic_category (category, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='选题目录';

CREATE TABLE IF NOT EXISTS godp_planning_batch (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '策划批次主键ID',
    batch_code VARCHAR(64) NOT NULL COMMENT '策划批次唯一编码',
    plan_type VARCHAR(16) NOT NULL COMMENT '策划类型：auto自动、manual手动',
    status VARCHAR(32) NOT NULL COMMENT '批次当前状态',
    cycle_start DATE NOT NULL COMMENT '策划周期开始日期',
    cycle_end DATE NOT NULL COMMENT '策划周期结束日期',
    account_count INT NOT NULL DEFAULT 0 COMMENT '批次涉及账号数量',
    content_count INT NOT NULL DEFAULT 0 COMMENT '批次已计入内容数量；演示记录为模拟值',
    note VARCHAR(500) NOT NULL DEFAULT '' COMMENT '批次备注说明',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_batch_code (batch_code),
    KEY idx_batch_cycle (cycle_start, cycle_end),
    KEY idx_batch_type (plan_type, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策划批次';

CREATE TABLE IF NOT EXISTS godp_planning_item (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '策划条目主键ID',
    batch_id BIGINT NOT NULL COMMENT '逻辑关联批次ID，无外键',
    account_id VARCHAR(64) NOT NULL COMMENT '客户账号唯一编码',
    account_name VARCHAR(120) NOT NULL COMMENT '策划时的账号名称快照',
    publish_date DATE NOT NULL COMMENT '计划投放日期',
    slot_type VARCHAR(32) NOT NULL COMMENT '槽位类型',
    topic_id VARCHAR(64) NOT NULL COMMENT '客户选题唯一编码；占位槽可为空',
    topic_title VARCHAR(255) NOT NULL COMMENT '策划时的选题标题快照',
    topic_type VARCHAR(16) NULL COMMENT '实际绑定选题的来源类型：普通、营销或热点；待定空槽为空',
    outline LONGTEXT NULL COMMENT '策划结果选题大纲快照；待定空槽为空',
    content_type VARCHAR(100) NULL COMMENT '策划结果内容类型快照；待定空槽为空',
    status VARCHAR(32) NOT NULL COMMENT '策划条目当前状态',
    lifecycle_stage VARCHAR(32) NULL COMMENT '策划时账号生命周期阶段快照',
    content_role VARCHAR(16) NULL COMMENT '策划时选题经营作用快照：流量或转化',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    KEY idx_item_batch (batch_id),
    KEY idx_item_account_date (account_id, publish_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策划槽位条目';

CREATE TABLE IF NOT EXISTS godp_auto_plan_run (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '自动策划运行记录主键ID',
    cycle_start DATE NOT NULL COMMENT '目标策划周期周一日期',
    cycle_end DATE NOT NULL COMMENT '目标策划周期周日日期',
    data_scope VARCHAR(16) NOT NULL COMMENT '输入数据范围：demo演示或live正式',
    plan_mode VARCHAR(32) NOT NULL COMMENT '策划方式：ordinary_fallback普通兜底或rule_fallback规则槽位加普通兜底',
    batch_id BIGINT NOT NULL COMMENT '逻辑关联策划批次ID，无外键',
    config_version INT NOT NULL COMMENT '运行启动时使用的全局配置版本号',
    config_json LONGTEXT NOT NULL COMMENT '运行启动时冻结的完整配置JSON',
    account_snapshot_json LONGTEXT NOT NULL COMMENT '参与账号及其来源版本和生命周期指标快照JSON',
    topic_snapshot_json LONGTEXT NOT NULL COMMENT '本次可用普通和营销选题及其来源版本快照JSON',
    account_count INT NOT NULL COMMENT '本次参与策划的账号数量',
    slot_count INT NOT NULL COMMENT '本次生成的全部自动策划槽位数量',
    status VARCHAR(24) NOT NULL COMMENT '运行状态：已规划或已完成',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_auto_plan_scope_cycle (data_scope, cycle_start, plan_mode),
    KEY idx_auto_plan_batch (batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自动策划运行与输入快照';

CREATE TABLE IF NOT EXISTS godp_account_source (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '账号来源记录主键ID',
    account_id VARCHAR(64) NOT NULL COMMENT '客户账号唯一编码',
    source_updated_at DATETIME(6) NOT NULL COMMENT '客户系统账号最后更新时间（UTC）',
    payload_json LONGTEXT NOT NULL COMMENT '客户账号同步原始内容JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_account_source_id (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户账号事实本地副本';

CREATE TABLE IF NOT EXISTS godp_topic_source (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '选题来源记录主键ID',
    topic_id VARCHAR(64) NOT NULL COMMENT '客户选题唯一编码',
    source_updated_at DATETIME(6) NOT NULL COMMENT '客户系统选题最后更新时间（UTC）',
    approval_status VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT '选题审核状态',
    valid_from DATETIME(6) NULL COMMENT '选题有效期开始时间（UTC）',
    valid_to DATETIME(6) NULL COMMENT '选题有效期结束时间（UTC）',
    payload_json LONGTEXT NOT NULL COMMENT '客户选题同步原始内容JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_topic_source_id (topic_id),
    KEY idx_topic_source_validity (approval_status, valid_from, valid_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户选题事实本地副本';

CREATE TABLE IF NOT EXISTS godp_marketing_topic_source (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '营销选题来源记录主键ID',
    topic_id VARCHAR(64) NOT NULL COMMENT '营销选题来源系统唯一编码',
    account_id VARCHAR(64) NOT NULL COMMENT '该营销选题绑定的客户账号编码',
    source_batch_id VARCHAR(64) NOT NULL COMMENT '最近一次包含该选题的营销同步批次编码',
    source_snapshot_at DATETIME(6) NOT NULL COMMENT '最近一次来源全量快照时间，按UTC保存',
    approval_status VARCHAR(16) NOT NULL COMMENT '营销选题审核状态：pending、approved或rejected',
    approved_at DATETIME(6) NULL COMMENT '营销选题审核通过时间，按UTC保存',
    valid_from DATETIME(6) NULL COMMENT '营销选题有效期开始时间，按UTC保存',
    valid_to DATETIME(6) NULL COMMENT '营销选题有效期结束时间，按UTC保存',
    enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '来源选题是否启用：1启用0停用',
    active_in_snapshot TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否出现在最近一次成功全量快照：1是0否',
    payload_json LONGTEXT NOT NULL COMMENT '营销选题完整来源记录JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_marketing_topic_source_id (topic_id),
    KEY idx_marketing_topic_account (account_id, active_in_snapshot, approval_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='IF-03营销选题及账号绑定的本地快照';

CREATE TABLE IF NOT EXISTS godp_marketing_sync_run (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '营销选题同步运行记录主键ID',
    source_batch_id VARCHAR(64) NOT NULL COMMENT '客户营销选题全量同步批次唯一编码',
    source_snapshot_at DATETIME(6) NOT NULL COMMENT '客户全量快照时间，按UTC保存',
    payload_json LONGTEXT NOT NULL COMMENT '营销选题全量同步请求内容JSON',
    result_json LONGTEXT NOT NULL COMMENT '营销选题同步结果和变更数量JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_marketing_sync_batch (source_batch_id),
    KEY idx_marketing_sync_snapshot (source_snapshot_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='IF-03营销选题全量同步成功记录';

CREATE TABLE IF NOT EXISTS godp_hotspot_topic_source (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '热点选题来源记录主键ID',
    topic_id VARCHAR(64) NOT NULL COMMENT '热点选题来源系统唯一编码',
    source_batch_id VARCHAR(64) NOT NULL COMMENT '最近一次包含该选题的热点同步批次编码',
    source_snapshot_at DATETIME(6) NOT NULL COMMENT '最近一次来源全量快照时间，按UTC保存',
    valid_from DATETIME(6) NULL COMMENT '热点选题有效期开始时间，按UTC保存',
    valid_to DATETIME(6) NULL COMMENT '热点选题有效期结束时间，按UTC保存',
    enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '来源选题是否启用：1启用0停用',
    active_in_snapshot TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否出现在最近一次成功全量快照：1是0否',
    payload_json LONGTEXT NOT NULL COMMENT '热点选题完整来源记录JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_hotspot_topic_source_id (topic_id),
    KEY idx_hotspot_topic_validity (active_in_snapshot, enabled, valid_from, valid_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='IF-04热点选题本地全量快照';

CREATE TABLE IF NOT EXISTS godp_hotspot_sync_run (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '热点选题同步运行记录主键ID',
    source_batch_id VARCHAR(64) NOT NULL COMMENT '客户热点选题全量同步批次唯一编码',
    source_snapshot_at DATETIME(6) NOT NULL COMMENT '客户全量快照时间，按UTC保存',
    payload_json LONGTEXT NOT NULL COMMENT '热点选题全量同步请求内容JSON',
    result_json LONGTEXT NOT NULL COMMENT '热点选题同步结果和变更数量JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_hotspot_sync_batch (source_batch_id),
    KEY idx_hotspot_sync_snapshot (source_snapshot_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='IF-04热点选题全量同步成功记录';

CREATE TABLE IF NOT EXISTS godp_content_history (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '历史内容记录主键ID',
    content_id VARCHAR(64) NOT NULL COMMENT '客户内容唯一编码',
    account_id VARCHAR(64) NOT NULL COMMENT '内容所属客户账号编码',
    topic_id VARCHAR(64) NOT NULL DEFAULT '' COMMENT '内容关联客户选题编码',
    published_at DATETIME(6) NULL COMMENT '内容实际发布时间（UTC）',
    source_updated_at DATETIME(6) NOT NULL COMMENT '客户系统内容最后更新时间（UTC）',
    payload_json LONGTEXT NOT NULL COMMENT '历史运营数据原始内容JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_content_history_id (content_id),
    KEY idx_content_history_account_time (account_id, published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户历史运营事实本地副本';

CREATE TABLE IF NOT EXISTS godp_slot_state (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '槽位状态记录主键ID',
    item_id BIGINT NOT NULL COMMENT '逻辑关联策划条目ID，无外键',
    slot_id VARCHAR(64) NOT NULL COMMENT '跨系统稳定槽位编码',
    version INT NOT NULL DEFAULT 1 COMMENT '槽位当前内容版本号',
    topic_id VARCHAR(64) NOT NULL DEFAULT '' COMMENT '当前版本绑定的客户选题编码',
    production_status VARCHAR(32) NOT NULL DEFAULT 'planned' COMMENT '当前版本内容生产状态',
    content_id VARCHAR(64) NULL COMMENT '客户内容生产系统返回的内容编码',
    generated_at DATETIME(6) NULL COMMENT '内容生成完成时间（UTC）',
    published_at DATETIME(6) NULL COMMENT '内容实际发布时间（UTC）',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_slot_state_item (item_id),
    UNIQUE KEY uk_slot_state_slot (slot_id),
    KEY idx_slot_state_topic (topic_id, production_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='本项目槽位当前版本和内容状态';

CREATE TABLE IF NOT EXISTS godp_integration_outbox (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '待投递事件记录主键ID',
    event_id VARCHAR(64) NOT NULL COMMENT '跨系统事件唯一编码',
    destination VARCHAR(32) NOT NULL COMMENT '事件接收系统标识',
    event_type VARCHAR(40) NOT NULL COMMENT '事件业务类型',
    payload_json LONGTEXT NOT NULL COMMENT '待投递事件完整内容JSON',
    delivery_status VARCHAR(24) NOT NULL DEFAULT 'pending' COMMENT '事件投递状态',
    attempts INT NOT NULL DEFAULT 0 COMMENT '已尝试投递次数',
    last_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '最近一次投递失败原因',
    delivered_at DATETIME(6) NULL COMMENT '事件成功投递时间（UTC）',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_outbox_event (event_id),
    KEY idx_outbox_delivery (delivery_status, destination, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='跨系统待投递事件';

CREATE TABLE IF NOT EXISTS godp_content_receipt (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '内容状态回传记录主键ID',
    event_id VARCHAR(64) NOT NULL COMMENT '客户回传事件唯一编码',
    slot_id VARCHAR(64) NOT NULL COMMENT '回传关联的稳定槽位编码',
    version INT NOT NULL COMMENT '回传关联的内容版本号',
    production_status VARCHAR(32) NOT NULL COMMENT '客户回传的内容生产状态',
    content_id VARCHAR(64) NULL COMMENT '客户内容生产系统的内容编码',
    payload_json LONGTEXT NOT NULL COMMENT '客户状态回传原始内容JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_content_receipt_event (event_id),
    KEY idx_content_receipt_slot (slot_id, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='内容生产状态回传记录';

CREATE TABLE IF NOT EXISTS godp_publication_receipt (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '发布状态回传记录主键ID',
    event_id VARCHAR(64) NOT NULL COMMENT '客户发布状态事件唯一编码',
    planning_result_id BIGINT NOT NULL COMMENT '关联策划结果条目ID，无外键',
    result_version INT NOT NULL COMMENT '客户确认的策划结果版本号',
    topic_id VARCHAR(64) NOT NULL COMMENT '客户实际发布的选题编码',
    topic_type VARCHAR(16) NOT NULL COMMENT '客户实际发布的选题类型：普通、营销或热点',
    publish_status VARCHAR(16) NOT NULL COMMENT '客户回传的发布状态：未发布或已发布',
    validation_status VARCHAR(16) NOT NULL COMMENT '回传校验结果：accepted通过或mismatch不一致',
    content_id VARCHAR(64) NULL COMMENT '客户内容系统中的内容编码',
    occurred_at DATETIME(6) NOT NULL COMMENT '客户发布状态发生时间，按UTC保存',
    payload_json LONGTEXT NOT NULL COMMENT '发布状态回传完整请求内容JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_publication_receipt_event (event_id),
    KEY idx_publication_receipt_result (planning_result_id, result_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户发布状态回传与一致性校验记录';

CREATE TABLE IF NOT EXISTS godp_topic_tag (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '选题标签记录主键ID',
    topic_id VARCHAR(64) NOT NULL COMMENT '客户选题唯一编码',
    version INT NOT NULL DEFAULT 1 COMMENT '选题标签当前版本号',
    tags_json LONGTEXT NOT NULL COMMENT '选题标签关联内容JSON',
    label_status VARCHAR(16) NOT NULL DEFAULT '处理中' COMMENT '普通选题T1到T6标签识别状态：处理中、已完成或失败',
    label_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '标签识别失败原因或空字符串',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_topic_tag_topic (topic_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='本项目识别和维护的选题标签';

CREATE TABLE IF NOT EXISTS godp_topic_official_usage (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '选题正式使用次数记录主键ID',
    topic_type VARCHAR(16) NOT NULL COMMENT '选题类型：普通、营销或热点',
    topic_id VARCHAR(64) NOT NULL COMMENT '对应类型命名空间内的选题唯一编码',
    official_use_count BIGINT NOT NULL DEFAULT 0 COMMENT '独立业务逻辑确认的正式使用次数',
    source_revision BIGINT NOT NULL COMMENT '独立计数来源的递增版本号',
    source_name VARCHAR(64) NOT NULL COMMENT '独立计数来源名称',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_official_usage_topic (topic_type, topic_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='独立维护的三类选题正式使用次数';

CREATE TABLE IF NOT EXISTS godp_topic_official_usage_history (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '正式使用次数变更记录主键ID',
    topic_type VARCHAR(16) NOT NULL COMMENT '选题类型：普通、营销或热点',
    topic_id VARCHAR(64) NOT NULL COMMENT '对应类型命名空间内的选题唯一编码',
    official_use_count BIGINT NOT NULL COMMENT '本次确认的正式使用次数快照',
    source_revision BIGINT NOT NULL COMMENT '独立计数来源的递增版本号',
    source_name VARCHAR(64) NOT NULL COMMENT '独立计数来源名称',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_official_usage_history_revision (topic_type, topic_id, source_revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='选题正式使用次数独立计数历史';

CREATE TABLE IF NOT EXISTS godp_strategy_config_version (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '配置快照记录主键ID',
    config_key VARCHAR(64) NOT NULL COMMENT '配置项唯一标识',
    version INT NOT NULL COMMENT '配置快照版本号',
    config_json LONGTEXT NOT NULL COMMENT '该版本完整配置内容JSON',
    action VARCHAR(32) NOT NULL COMMENT '版本生成动作：保存或恢复',
    source_version INT NULL COMMENT '恢复动作引用的历史版本号',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_config_version (config_key, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='运营配置不可变历史快照';

CREATE TABLE IF NOT EXISTS godp_manual_preview (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '手动策划预览记录主键ID',
    preview_code VARCHAR(64) NOT NULL COMMENT '手动策划预览唯一编码',
    publish_date DATE NOT NULL COMMENT '本次策划统一投放日期',
    allocations_json LONGTEXT NOT NULL COMMENT '账号与选题的确定分配结果JSON',
    note VARCHAR(500) NOT NULL DEFAULT '' COMMENT '手动策划备注说明',
    status VARCHAR(24) NOT NULL DEFAULT 'pending' COMMENT '预览状态：待提交或已提交',
    expires_at DATETIME NOT NULL COMMENT '预览结果失效时间（UTC）',
    batch_id BIGINT NULL COMMENT '提交后关联的策划批次ID',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_manual_preview_code (preview_code),
    KEY idx_manual_preview_status (status, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='手动策划确定分配预览';

CREATE TABLE IF NOT EXISTS godp_manual_task (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '手动策划任务主键ID',
    task_code VARCHAR(64) NOT NULL COMMENT '手动策划任务唯一编码',
    preview_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '关联的手动策划预览编码',
    publish_date DATE NOT NULL COMMENT '本次任务投放日期',
    planned_account_count INT NOT NULL DEFAULT 0 COMMENT '规划账号数量',
    result_count INT NOT NULL DEFAULT 0 COMMENT '成功落库结果数量',
    failure_count INT NOT NULL DEFAULT 0 COMMENT '未成功形成结果数量',
    topic_count INT NOT NULL DEFAULT 0 COMMENT '本次选择的选题数量',
    status VARCHAR(24) NOT NULL COMMENT '任务状态：执行中、已完成、执行失败',
    failure_reason VARCHAR(500) NOT NULL DEFAULT '' COMMENT '任务失败原因',
    batch_id BIGINT NULL COMMENT '成功后关联的策划批次ID',
    last_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '最近一次执行异常说明',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '发起时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '发起人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '最后更新人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_manual_task_code (task_code),
    KEY idx_manual_task_status (status, update_time),
    KEY idx_manual_task_date (publish_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='手动策划任务记录';

CREATE TABLE IF NOT EXISTS godp_planning_adjustment (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '策划调整记录主键ID',
    item_id BIGINT NOT NULL COMMENT '逻辑关联策划条目ID，无外键',
    result_version INT NOT NULL COMMENT '调整后结果版本号',
    adjustment_source VARCHAR(24) NOT NULL COMMENT '调整来源：人工替换、热点触发或热点替换',
    old_topic_id VARCHAR(64) NOT NULL DEFAULT '' COMMENT '调整前选题编码',
    old_topic_title VARCHAR(255) NOT NULL DEFAULT '' COMMENT '调整前选题标题',
    new_topic_id VARCHAR(64) NOT NULL COMMENT '调整后选题编码',
    new_topic_title VARCHAR(255) NOT NULL COMMENT '调整后选题标题',
    reason VARCHAR(500) NOT NULL DEFAULT '' COMMENT '人工或系统自动调整原因',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '调整时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '调整人或系统来源',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人或系统来源',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    KEY idx_adjustment_item (item_id, id),
    KEY idx_adjustment_source (adjustment_source, create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策划结果人工与热点调整历史';

