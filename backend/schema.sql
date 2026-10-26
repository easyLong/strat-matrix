-- MySQL schema. Run explicitly after confirming the target database.
-- No foreign keys, stored procedures, functions, or views.

CREATE TABLE IF NOT EXISTS godp_system_config (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '系统配置记录主键ID',
    config_key VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT '系统配置唯一键，区分大小写并沿用原配置项名称',
    config_group VARCHAR(64) NOT NULL COMMENT '配置分组：服务端口、模型名称或鉴权密钥',
    config_name VARCHAR(200) NOT NULL COMMENT '配置项中文名称及用途',
    config_value MEDIUMTEXT NOT NULL COMMENT '配置值文本，按值类型解析；密钥仅供受控服务端读取',
    value_type VARCHAR(16) NOT NULL DEFAULT 'string' COMMENT '配置值类型：string字符串、int整数、bool开关',
    is_secret TINYINT NOT NULL DEFAULT 0 COMMENT '是否敏感配置：1为密钥或令牌，查询展示时脱敏',
    enabled TINYINT NOT NULL DEFAULT 1 COMMENT '配置启用标记：1启用、0停用；停用参数禁止读取',
    version INT NOT NULL DEFAULT 1 COMMENT '配置版本号，每次修改递增，用于并发更新校验',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '配置创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '配置创建人或初始化进程',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '配置最后修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '配置最后修改人或更新进程',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '逻辑删除标志：N正常、Y删除',
    UNIQUE KEY uk_system_config_key (config_key),
    KEY idx_system_config_group (config_group, del_flag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='服务监听地址与端口、模型名称及鉴权密钥配置；MySQL连接信息单独保存在.env';

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
    persona VARCHAR(500) NOT NULL DEFAULT '' COMMENT '账号人设描述，用于账号画像与选题匹配',
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
    active_in_snapshot TINYINT(1) NOT NULL DEFAULT 1 COMMENT '账号来源记录当前是否有效：1有效0已被全量快照停用',
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
    active_in_snapshot TINYINT(1) NOT NULL DEFAULT 1 COMMENT '普通选题来源记录当前是否有效：1有效0已被全量快照停用',
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

CREATE TABLE IF NOT EXISTS godp_source_sync_run (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '账号或普通选题全量同步运行记录主键ID',
    source_type VARCHAR(16) NOT NULL COMMENT '来源数据类型：account账号或topic普通选题',
    source_batch_id VARCHAR(64) NOT NULL COMMENT '客户全量同步批次唯一编码',
    source_snapshot_at DATETIME(6) NOT NULL COMMENT '客户全量快照时间或服务端接收时间，按UTC保存',
    payload_json LONGTEXT NOT NULL COMMENT '本次全量同步完整请求内容JSON',
    result_json LONGTEXT NOT NULL COMMENT '本次全量同步入库及停用数量JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'integration' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_source_sync_type_batch (source_type, source_batch_id),
    KEY idx_source_sync_snapshot (source_type, source_snapshot_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='IF-01与IF-02成功全量快照记录';

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
    tag_ids_json LONGTEXT NULL COMMENT '选题已识别T1到T5标签稳定ID映射JSON；旧数据可部分解析',
    taxonomy_version INT NULL COMMENT '本次标签识别使用的T1到T5字典版本；旧记录未知时为空',
    t6_tag_id BIGINT NULL COMMENT '识别后复用或新增的T6用户需求标签稳定ID；旧记录未解析时为空',
    label_status VARCHAR(16) NOT NULL DEFAULT '处理中' COMMENT '普通选题T1到T6标签识别状态：处理中、已完成或失败',
    label_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '标签识别失败原因或空字符串',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_topic_tag_topic (topic_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='本项目识别和维护的选题标签';

CREATE TABLE IF NOT EXISTS godp_topic_tag_history (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '选题标签历史快照主键ID',
    topic_id VARCHAR(64) NOT NULL COMMENT '客户普通选题唯一编码',
    version INT NOT NULL COMMENT '该选题标签结果版本号',
    tags_json LONGTEXT NOT NULL COMMENT '该版本T1到T6标签名称快照JSON',
    tag_ids_json LONGTEXT NOT NULL COMMENT '该版本T1到T5标签稳定ID映射JSON',
    taxonomy_version INT NULL COMMENT '该版本标签识别所用字典版本；旧记录未知时为空',
    t6_tag_id BIGINT NULL COMMENT '该版本关联的T6用户需求标签稳定ID；旧历史未解析时为空',
    label_status VARCHAR(16) NOT NULL COMMENT '该版本标签识别状态',
    label_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '该版本标签识别失败原因或空字符串',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_topic_tag_history_version (topic_id, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='普通选题标签名称与稳定ID的版本历史';

CREATE TABLE IF NOT EXISTS godp_t6_tag (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT 'T6用户需求标签稳定ID',
    name VARCHAR(80) NOT NULL COMMENT 'T6用户需求标签名称',
    embedding_model VARCHAR(100) NULL COMMENT '该标签语义向量所使用的模型标识；旧标签无向量时为空',
    embedding_json LONGTEXT NULL COMMENT '该标签在对应模型下的语义向量JSON；旧标签无向量时为空',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_t6_tag_name (name),
    KEY idx_t6_tag_embedding_model (embedding_model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='普通选题T6用户需求标签及语义向量库';

CREATE TABLE IF NOT EXISTS godp_matching_policy (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '普通内容匹配算法策略版本主键ID',
    policy_key VARCHAR(32) NOT NULL COMMENT '算法策略系列唯一标识',
    version INT NOT NULL COMMENT '同一策略系列的递增版本号',
    document_json LONGTEXT NOT NULL COMMENT '该版本明确规则、参数、输入依赖及验收样例完整JSON，不允许原地修改',
    document_hash CHAR(64) NOT NULL COMMENT '不可变算法策略文档SHA256指纹',
    status VARCHAR(16) NOT NULL DEFAULT 'draft' COMMENT '策略状态：draft待确认、approved已确认可绑定任务或disabled已停用',
    confirmed_by VARCHAR(50) NULL COMMENT '内部接口提交的规则确认人标识；不是单点登录身份认证',
    confirmed_at DATETIME(6) NULL COMMENT '策略规则确认时间，按UTC保存',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_matching_policy_version (policy_key, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='普通内容匹配算法不可变策略版本与确认记录';

CREATE TABLE IF NOT EXISTS godp_matching_task (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '普通内容匹配内部执行任务主键ID',
    preparation_id BIGINT NOT NULL COMMENT '逻辑关联已冻结AI准备记录ID，无外键',
    preparation_version INT NOT NULL COMMENT '创建任务时绑定的AI准备记录版本',
    preparation_input_hash CHAR(64) NOT NULL COMMENT '创建任务时绑定的完整准备输入指纹',
    policy_id BIGINT NOT NULL COMMENT '逻辑关联已确认的算法策略版本ID，无外键',
    policy_hash CHAR(64) NOT NULL COMMENT '执行任务绑定的不可变算法策略指纹',
    input_hash CHAR(64) NOT NULL COMMENT '契约版本、准备输入与策略身份组合SHA256指纹',
    contract_version INT NOT NULL DEFAULT 1 COMMENT '匹配任务契约版本：1基础输入或2含补充事实快照',
    supplemental_hash CHAR(64) NULL COMMENT '第二版任务绑定的兜底、历史和正式计数补充输入指纹；第一版为空',
    status VARCHAR(16) NOT NULL DEFAULT 'queued' COMMENT '任务状态：queued待执行、processing处理中、evaluated提案已保存、failed执行失败、cancelled取消或invalidated输入失效',
    version INT NOT NULL DEFAULT 1 COMMENT '任务递增状态版本，用于重试并发校验',
    attempt_count INT NOT NULL DEFAULT 0 COMMENT '执行任务累计领取次数',
    lease_id CHAR(32) NULL COMMENT '当前执行尝试租约唯一标识',
    lease_expires_at DATETIME(6) NULL COMMENT '当前租约到期时间，按UTC保存',
    error_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '最近一次内部异常原因码，不保存模型错误正文',
    result_json LONGTEXT NULL COMMENT '通过契约校验的普通内容匹配提案及逐阶段记录JSON，尚未提交运营结果',
    result_hash CHAR(64) NULL COMMENT '已保存执行提案SHA256指纹，用于重复回写校验',
    completed_at DATETIME(6) NULL COMMENT '首次提案回写成功时间，按UTC保存',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_matching_task_preparation (preparation_id),
    KEY idx_matching_task_queue (status, lease_expires_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='普通内容匹配提案内部执行队列，不是运营策划批次';

CREATE TABLE IF NOT EXISTS godp_matching_input_snapshot (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '匹配任务补充事实输入快照主键ID',
    task_id BIGINT NOT NULL COMMENT '逻辑关联第二版匹配任务ID，无外键；每个任务仅冻结一次',
    as_of DATETIME(6) NOT NULL COMMENT '历史窗口截止及补充输入首次读取时点，按UTC保存',
    snapshot_json LONGTEXT NOT NULL COMMENT '本任务冻结的兜底选题、历史事实及正式使用计数JSON，未知值不补零',
    snapshot_hash CHAR(64) NOT NULL COMMENT '完整补充事实快照SHA256指纹',
    counts_json LONGTEXT NOT NULL COMMENT '声明的补充输入数量、未知计数及历史覆盖状态摘要JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_matching_input_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='普通匹配任务不可变的兜底、历史和正式使用计数事实快照';

CREATE TABLE IF NOT EXISTS godp_matching_attempt (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '普通内容匹配执行尝试主键ID',
    task_id BIGINT NOT NULL COMMENT '逻辑关联内部匹配任务ID，无外键',
    attempt_number INT NOT NULL COMMENT '同一执行任务的领取序号',
    lease_id CHAR(32) NOT NULL COMMENT '本次尝试唯一租约标识，旧尝试不能回写新尝试',
    lease_expires_at DATETIME(6) NOT NULL COMMENT '本次尝试租约到期时间，按UTC保存',
    status VARCHAR(16) NOT NULL DEFAULT 'processing' COMMENT '尝试状态：processing执行中、evaluated提案已保存、failed执行失败或expired租约过期',
    error_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '本次执行失败或失效原因码',
    completed_at DATETIME(6) NULL COMMENT '本次尝试结束时间，按UTC保存',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_matching_attempt_sequence (task_id, attempt_number),
    UNIQUE KEY uk_matching_attempt_lease (lease_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='普通内容匹配每次领取、续租、异常与过期的执行历史';

CREATE TABLE IF NOT EXISTS godp_ai_preparation (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '正式AI策划内部准备记录主键ID，与运营批次ID独立',
    preparation_code VARCHAR(64) NOT NULL COMMENT '内部准备记录唯一编码',
    reservation_key VARCHAR(64) NULL COMMENT '正式周期占用键；取消或过期后为空以释放周期',
    cycle_start DATE NOT NULL COMMENT '目标策划周期开始日期，必须为周一',
    cycle_end DATE NOT NULL COMMENT '目标策划周期结束日期，按北京时间判断过期',
    status VARCHAR(24) NOT NULL DEFAULT 'waiting_inputs' COMMENT '内部状态：waiting_inputs等待输入、blocked输入异常、inputs_frozen输入已冻结、cancelled已取消或expired已过期',
    version INT NOT NULL DEFAULT 1 COMMENT '准备记录递增版本号，用于推进和取消操作的并发校验',
    selection_json LONGTEXT NOT NULL COMMENT '创建请求的账号选择JSON；null表示全部正式可用账号',
    config_version INT NOT NULL COMMENT '创建准备记录时冻结的运营配置版本',
    config_json LONGTEXT NOT NULL COMMENT '创建准备记录时冻结的完整运营配置JSON',
    account_snapshot_json LONGTEXT NOT NULL COMMENT '本次冻结的账号事实、互动、指标、阶段及经营目标JSON',
    slot_blueprint_json LONGTEXT NOT NULL COMMENT '账号与投放日期安排JSON；尚未确定槽位类型和选题',
    account_count INT NOT NULL COMMENT '冻结的参与账号数量',
    slot_count INT NOT NULL COMMENT '冻结的日期安排数量，不代表已生成策划槽位',
    topic_count INT NOT NULL DEFAULT 0 COMMENT '冻结的兼容普通选题数量；未冻结时为零',
    input_hash CHAR(64) NULL COMMENT '完整账号、配置、日期及选题输入的SHA256指纹；冻结前为空',
    frozen_at DATETIME(6) NULL COMMENT '匹配输入冻结时间，按UTC保存',
    attempt_count INT NOT NULL DEFAULT 0 COMMENT '已执行输入检查和推进的次数',
    last_report_json LONGTEXT NULL COMMENT '最近一次就绪检查报告JSON，包含内部阻断原因',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_ai_preparation_code (preparation_code),
    UNIQUE KEY uk_ai_preparation_reservation (reservation_key),
    KEY idx_ai_preparation_cycle (cycle_start, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='正式AI策划结果生成前的内部输入准备与周期占用';

CREATE TABLE IF NOT EXISTS godp_ai_preparation_account (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT 'AI准备记录账号画像主键ID',
    preparation_id BIGINT NOT NULL COMMENT '逻辑关联内部AI准备记录ID，无外键；不是运营批次ID',
    account_id VARCHAR(64) NOT NULL COMMENT '冻结的客户账号唯一编码',
    config_version INT NOT NULL COMMENT '本次账号画像使用的冻结运营配置版本',
    source_updated_at DATETIME(6) NOT NULL COMMENT '账号来源版本时间，按UTC保存',
    profile_hash CHAR(64) NOT NULL COMMENT '内部准备身份、配置和账号输入画像的SHA256指纹',
    snapshot_json LONGTEXT NOT NULL COMMENT '本次冻结的完整账号输入JSON',
    profile_json LONGTEXT NOT NULL COMMENT '由本次账号快照构建的画像JSON',
    vector_json LONGTEXT NULL COMMENT '本次账号画像单位向量JSON；待生成或失败时为空',
    vector_model VARCHAR(100) NULL COMMENT '账号向量模型及版本标识',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '向量准备状态：pending待生成、ready已就绪或failed失败可重试',
    last_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '最近一次向量生成失败原因或空字符串',
    completed_at DATETIME(6) NULL COMMENT '账号向量生成完成时间，按UTC保存',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_ai_preparation_account (preparation_id, account_id),
    KEY idx_ai_preparation_account_jobs (status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='正式AI准备记录独立冻结的账号画像及向量任务';

CREATE TABLE IF NOT EXISTS godp_ai_preparation_topic (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT 'AI准备记录冻结选题主键ID',
    preparation_id BIGINT NOT NULL COMMENT '逻辑关联内部AI准备记录ID，无外键',
    topic_id VARCHAR(64) NOT NULL COMMENT '冻结的正式普通选题唯一编码',
    snapshot_json LONGTEXT NOT NULL COMMENT '冻结的来源、有效期、标签稳定ID及版本、画像指纹和向量完整JSON',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_ai_preparation_topic (preparation_id, topic_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='正式AI准备记录不可变的兼容普通选题输入快照';

CREATE TABLE IF NOT EXISTS godp_account_profile (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '批次账号画像与向量记录主键ID',
    batch_id BIGINT NOT NULL COMMENT '逻辑关联策划批次ID，无外键；画像仅供该批次使用',
    account_id VARCHAR(64) NOT NULL COMMENT '参与该批次策划的客户账号唯一编码',
    config_version INT NOT NULL COMMENT '该批次冻结的策划配置版本号',
    source_updated_at DATETIME(6) NOT NULL COMMENT '该批次读取的账号来源版本时间，按UTC保存',
    profile_hash CHAR(64) NOT NULL COMMENT '批次身份、配置版本和完整账号输入画像的SHA256指纹',
    snapshot_json LONGTEXT NOT NULL COMMENT '该批次冻结的账号事实、互动明细、指标、阶段与经营目标JSON',
    profile_json LONGTEXT NOT NULL COMMENT '仅由该批次账号输入快照构建的画像JSON',
    vector_json LONGTEXT NULL COMMENT '该批次账号画像单位向量JSON；待生成或失败时为空',
    vector_model VARCHAR(100) NULL COMMENT '账号向量模型及版本标识；须与匹配选题使用相同向量空间',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '账号向量准备状态：pending待生成、ready已就绪或failed生成失败',
    last_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '最近一次账号向量生成失败原因或空字符串',
    completed_at DATETIME(6) NULL COMMENT '该批次账号向量生成完成时间，按UTC保存',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_account_profile_batch_account (batch_id, account_id),
    KEY idx_account_profile_status (status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='按策划批次冻结的账号画像与向量准备状态';

CREATE TABLE IF NOT EXISTS godp_topic_profile (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '普通选题画像和向量记录主键ID',
    topic_id VARCHAR(64) NOT NULL COMMENT '客户普通选题唯一编码',
    content_hash CHAR(64) NOT NULL COMMENT '当前有效内容与T1到T6标签画像的SHA256指纹',
    tag_version INT NOT NULL COMMENT '画像使用的普通选题标签结果版本号',
    profile_json LONGTEXT NOT NULL COMMENT '由当前有效选题内容与标签构建的画像JSON',
    vector_json LONGTEXT NULL COMMENT '当前画像对应的选题向量JSON；待生成或失效时为空',
    vector_model VARCHAR(100) NULL COMMENT '当前选题向量所使用的模型标识；待生成或失效时为空',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '向量准备状态：pending待生成、ready已就绪或failed生成失败',
    last_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '最近一次向量生成失败原因或空字符串',
    completed_at DATETIME(6) NULL COMMENT '当前画像向量生成完成时间，按UTC保存',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_topic_profile_topic (topic_id),
    KEY idx_topic_profile_status (status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='普通选题当前内容版本的画像与向量准备状态';

CREATE TABLE IF NOT EXISTS godp_topic_label_job (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '普通选题首次离线标签识别任务主键ID',
    topic_id VARCHAR(64) NOT NULL COMMENT '客户普通选题唯一编码',
    source_payload_json LONGTEXT NOT NULL COMMENT '首次入库时普通选题来源内容快照JSON',
    source_updated_at DATETIME(6) NOT NULL COMMENT '首次入库时来源记录更新时间，按UTC保存',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending待领取、processing处理中、completed已完成、failed失败或cancelled已取消',
    attempt_count INT NOT NULL DEFAULT 0 COMMENT '任务已领取次数',
    lease_id VARCHAR(64) NULL COMMENT '当前处理租约唯一编码',
    lease_expires_at DATETIME(6) NULL COMMENT '当前处理租约到期时间，按UTC保存',
    taxonomy_version INT NULL COMMENT '当前处理尝试锁定的T1到T5字典版本',
    last_error VARCHAR(500) NOT NULL DEFAULT '' COMMENT '最近一次识别失败原因或空字符串',
    completed_at DATETIME(6) NULL COMMENT '首次成功完成标签识别时间，按UTC保存',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_topic_label_job_topic (topic_id),
    KEY idx_topic_label_job_status (status, lease_expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='普通选题首次离线标签识别任务及重试状态';

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
    task_name VARCHAR(120) NOT NULL DEFAULT '' COMMENT '手动策划任务名称',
    content_mode VARCHAR(24) NOT NULL DEFAULT 'legacy' COMMENT '人工策划内容模式：non_marketing非营销，legacy历史混合选题流程',
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
    task_name VARCHAR(120) NOT NULL DEFAULT '' COMMENT '手动策划任务名称',
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

