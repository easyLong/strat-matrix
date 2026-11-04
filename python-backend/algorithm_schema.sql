-- Python算法库首次安装：25张算法自有表，无Java业务表、原始资料表或演示数据。
-- 自动生成：python -m app.algorithm_schema export --output algorithm_schema.sql
-- 仅CREATE IF NOT EXISTS；不升级已有表字段，不删除表，不初始化/批准算法策略。

-- configuration
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

CREATE TABLE IF NOT EXISTS godp_algorithm_config_command (
    command_id VARCHAR(64) NOT NULL PRIMARY KEY COMMENT 'Java配置发布命令编号，重试保持不变',
    request_hash CHAR(64) NOT NULL COMMENT '配置命令请求指纹',
    result_json LONGTEXT NOT NULL COMMENT '算法配置应用后的版本及配置响应快照',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '配置命令应用时间，UTC'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='算法配置命令幂等接收记录';

-- features
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

CREATE TABLE IF NOT EXISTS godp_topic_label_job (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '普通选题首次离线标签识别任务主键ID',
    topic_id VARCHAR(64) NOT NULL COMMENT '客户普通选题唯一编码',
    source_payload_json LONGTEXT NOT NULL COMMENT '当前待识别或已识别普通选题的计算输入快照JSON',
    source_updated_at DATETIME(6) NOT NULL COMMENT '当前计算输入的来源记录更新时间，按UTC保存',
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

CREATE TABLE IF NOT EXISTS godp_account_mapping_rule (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '账号标准画像映射规则主键ID',
    mapping_version INT NOT NULL COMMENT '策划侧映射规则集版本，调用方显式指定',
    taxonomy_version INT NOT NULL COMMENT '规则绑定的选题标签词表版本',
    source_field VARCHAR(32) NOT NULL COMMENT '账号原始字段：persona人设、family_identity家庭身份、interests兴趣、gender性别、expression_style表达风格',
    source_value VARCHAR(200) NOT NULL COMMENT '精确匹配的原始字段值，不按名称相似度推断',
    target_dimension VARCHAR(8) NOT NULL COMMENT '映射维度：T3内容主题、T4目标客群、T5使用场景、T6需求能力、STYLE表达风格',
    target_level VARCHAR(8) NOT NULL COMMENT '目标层级：L2分类、L3末级标签、TEXT独立文本',
    target_node_id VARCHAR(64) NOT NULL DEFAULT '' COMMENT '选题标签稳定ID，文本规则为空，不使用演示Code',
    target_name VARCHAR(200) NOT NULL DEFAULT '' COMMENT '初始化时目标节点名称，展示名称以绑定词表为准',
    relation_type VARCHAR(16) NOT NULL COMMENT '适配关系：CORE核心、ADJACENT相邻、CONDITIONAL条件、OFF排除、TEXT文本',
    weight DECIMAL(4,2) NULL COMMENT '能力权重：核心1.00、相邻0.75、条件0.45、排除0.00，文本规则为空',
    condition_text VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '条件适配的明确使用条件，需由后续精判确认',
    target_text VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '账号需求服务能力或表达风格描述，不并入结构化标签树',
    status VARCHAR(16) NOT NULL DEFAULT 'draft' COMMENT '规则状态：draft待确认、active生效、disabled停用；待确认仅用于预览',
    source_reference VARCHAR(200) NOT NULL DEFAULT '' COMMENT '规则来源文档或人工维护依据',
    remark VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '规则解释、补充说明和待确认事项',
    create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '规则创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'account-mapping-init' COMMENT '规则创建人或初始化进程',
    update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '规则最后修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'account-mapping-init' COMMENT '规则最后修改人或维护进程',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '逻辑删除标志：N正常、Y删除',
    UNIQUE KEY uk_account_mapping_target (mapping_version, taxonomy_version, source_field, source_value, target_dimension, target_node_id),
    KEY idx_account_mapping_version (mapping_version, taxonomy_version, status, del_flag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='策划侧账号原始信息到标准标签及需求能力的映射规则';

-- preparation
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
    business_config_version INT NULL COMMENT 'Java业务任务冻结的生成规则版本，旧任务为空',
    business_config_json LONGTEXT NULL COMMENT 'Java业务任务冻结的策划日调度时间营销上限与热点占比快照',
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

CREATE TABLE IF NOT EXISTS godp_ai_preparation_progress (
  preparation_id BIGINT NOT NULL PRIMARY KEY COMMENT '准备任务主键，关联账号和候选选题范围',
  scope_json LONGTEXT NOT NULL COMMENT '任务固定输入范围及标签字典和模型版本，不含密钥',
  scope_hash CHAR(64) NOT NULL COMMENT '任务输入范围的完整性校验指纹',
  progress_json LONGTEXT NOT NULL COMMENT '分批准备阶段、分页断点、统计及等待原因',
  create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '任务准备进度创建时间',
  update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '任务准备进度最后更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策划任务输入范围与分批准备进度';

-- matching
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

CREATE TABLE IF NOT EXISTS godp_matching_ai_cache (
    cache_key CHAR(64) NOT NULL PRIMARY KEY COMMENT '模型结果缓存唯一指纹，包含输入、词表、映射、提示词和模型版本',
    task_kind VARCHAR(32) NOT NULL COMMENT '结果种类：账号映射、选题主关联标签、需求向量或配对精判',
    model_name VARCHAR(100) NOT NULL COMMENT '生成该结果的文本或向量模型名称',
    prompt_version VARCHAR(64) NOT NULL COMMENT '提示词及模型结果校验契约版本',
    taxonomy_version INT NOT NULL COMMENT '绑定的标签词表版本',
    mapping_version INT NOT NULL COMMENT '绑定的账号映射版本',
    result_json LONGTEXT NOT NULL COMMENT '校验通过的模型结果，不保存密钥，失败结果不缓存',
    result_hash CHAR(64) NOT NULL COMMENT '模型结果完整性校验指纹',
    create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '缓存首次创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'matching-quality-worker' COMMENT '缓存创建进程',
    KEY idx_matching_ai_cache_kind (task_kind, model_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策划匹配模型结果不可变缓存';

CREATE TABLE IF NOT EXISTS godp_matching_quality_run (
    task_id BIGINT NOT NULL PRIMARY KEY COMMENT '关联现有匹配任务ID，不另建任务队列',
    lease_id CHAR(32) NOT NULL COMMENT '本次写入对应的现有匹配任务租约',
    status VARCHAR(16) NOT NULL COMMENT '质量准备状态：processing处理中、waiting分批等待、ready已就绪、failed失败',
    phase VARCHAR(32) NOT NULL COMMENT '当前阶段：选题标签、账号映射、五路召回、模型精判或分配',
    report_json LONGTEXT NOT NULL COMMENT '分批进度、主关联标签、映射证据、召回及逐对精判结果',
    report_hash CHAR(64) NOT NULL COMMENT '过程报告完整性校验指纹',
    create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '过程记录首次创建时间',
    update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '过程记录最后更新时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'matching-quality-worker' COMMENT '过程记录更新进程'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='匹配任务V19适配质量执行进度与审计';

-- execution
CREATE TABLE IF NOT EXISTS godp_planning_pipeline_run (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT 'Pipeline运行记录主键ID',
    pipeline_code VARCHAR(64) NOT NULL COMMENT 'Pipeline运行唯一编码',
    reservation_key VARCHAR(64) NULL COMMENT '正式策划周期占用键；取消后置空以允许重建',
    schema_version INT NOT NULL DEFAULT 1 COMMENT 'Pipeline编排契约版本，第一版固定为1',
    cycle_start DATE NOT NULL COMMENT '目标策划周期开始日期，必须为周一',
    cycle_end DATE NOT NULL COMMENT '目标策划周期结束日期，固定为开始日期后六天',
    selection_json LONGTEXT NOT NULL COMMENT '参与账号编码有序JSON；null表示使用全部可用正式账号',
    selection_hash CHAR(64) NOT NULL COMMENT '参与账号范围JSON的SHA256指纹',
    policy_id BIGINT NOT NULL COMMENT '逻辑关联已确认匹配策略版本ID，无外键',
    planning_scope VARCHAR(20) NOT NULL DEFAULT 'full' COMMENT '策划范围：full普通营销热点组合，ordinary_only仅普通选题',
    production_provider VARCHAR(20) NOT NULL DEFAULT 'disabled' COMMENT '正式结果下游生产方式：disabled不自动生产，local_mock本地模拟内容方',
    commit_owner VARCHAR(12) NOT NULL DEFAULT 'python' COMMENT '正式结果提交归属，python旧流程或java业务库，创建后固定',
    business_config_version INT NULL COMMENT 'Java业务任务冻结的生成规则版本，旧任务为空',
    business_config_json LONGTEXT NULL COMMENT 'Java业务任务冻结的策划日调度时间营销上限与热点占比快照',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'Pipeline状态：pending、running、waiting、succeeded、failed或cancelled',
    current_stage VARCHAR(40) NULL COMMENT '当前依赖前沿中的首个阶段标识；完成或取消后为空',
    version INT NOT NULL DEFAULT 1 COMMENT 'Pipeline乐观锁版本号，每次编排状态变更递增',
    preparation_id BIGINT NULL COMMENT '逻辑关联AI准备记录ID，无外键',
    matching_task_id BIGINT NULL COMMENT '逻辑关联匹配执行任务ID，无外键',
    production_batch_id BIGINT NULL COMMENT '提交后关联策划批次ID，按commit_owner区分业务库或旧算法库；提交前为空',
    last_error_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '当前首个失败阶段错误码；无失败为空字符串',
    last_error_message VARCHAR(500) NOT NULL DEFAULT '' COMMENT '当前首个失败阶段可展示错误说明；无失败为空字符串',
    create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，按UTC保存',
    create_by VARCHAR(50) NOT NULL DEFAULT 'planning-pipeline-api' COMMENT '创建来源',
    update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '修改时间，按UTC保存',
    update_by VARCHAR(50) NOT NULL DEFAULT 'planning-pipeline-api' COMMENT '最后修改来源',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_planning_pipeline_code (pipeline_code),
    UNIQUE KEY uk_planning_pipeline_reservation (reservation_key),
    KEY idx_planning_pipeline_cycle (cycle_start, status, id),
    KEY idx_planning_pipeline_preparation (preparation_id),
    KEY idx_planning_pipeline_matching_task (matching_task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='正式智能策划Pipeline统一运行状态与下游执行引用';

CREATE TABLE IF NOT EXISTS godp_planning_stage_run (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT 'Pipeline阶段运行记录主键ID',
    pipeline_id BIGINT NOT NULL COMMENT '逻辑关联Pipeline运行记录ID，无外键',
    stage_key VARCHAR(40) NOT NULL COMMENT '阶段稳定标识：数据接入、双侧准备、匹配、分配、组合或提交',
    stage_order INT NOT NULL COMMENT '阶段展示顺序；依赖关系由代码契约定义而非单纯顺序定义',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '阶段状态：pending、running、waiting、succeeded、failed或cancelled',
    attempt_count INT NOT NULL DEFAULT 0 COMMENT '阶段进入等待或运行态的启动及重试次数',
    version INT NOT NULL DEFAULT 1 COMMENT '阶段乐观锁观察版本，每次阶段状态内容变更递增',
    backend_type VARCHAR(32) NULL COMMENT '复用后端类型：ai_preparation、matching_task、planning_batch或空',
    backend_id BIGINT NULL COMMENT '逻辑关联复用后端记录ID，无外键',
    detail_json LONGTEXT NULL COMMENT '阶段状态摘要JSON，仅保存可审计摘要不保存模型密钥',
    error_code VARCHAR(64) NOT NULL DEFAULT '' COMMENT '阶段失败或等待原因码；无原因为空字符串',
    error_message VARCHAR(500) NOT NULL DEFAULT '' COMMENT '阶段失败或等待的可展示说明；无原因为空字符串',
    started_at DATETIME(6) NULL COMMENT '阶段首次进入等待或运行态的时间，按UTC保存',
    finished_at DATETIME(6) NULL COMMENT '阶段成功、失败或取消的最近结束时间，按UTC保存',
    create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，按UTC保存',
    create_by VARCHAR(50) NOT NULL DEFAULT 'planning-pipeline-api' COMMENT '创建来源',
    update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '修改时间，按UTC保存',
    update_by VARCHAR(50) NOT NULL DEFAULT 'planning-pipeline-api' COMMENT '最后修改来源',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_planning_stage_key (pipeline_id, stage_key),
    KEY idx_planning_stage_status (status, pipeline_id, stage_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='正式智能策划Pipeline各阶段生命周期、重试与后端引用';

CREATE TABLE IF NOT EXISTS godp_algorithm_proposal (
    pipeline_id BIGINT NOT NULL PRIMARY KEY COMMENT '所属算法Pipeline编号，一个Pipeline仅冻结一份提案',
    proposal_hash CHAR(64) NOT NULL COMMENT '提案规范JSON原始字节的SHA256指纹',
    proposal_json LONGTEXT NOT NULL COMMENT '冻结的算法提案规范JSON，确认及重试期间保持不变',
    business_config_version INT NOT NULL COMMENT 'Java冻结业务配置版本',
    business_batch_id BIGINT NULL COMMENT 'Java业务库确认写入后的批次编号，仅保存引用',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '提案冻结时间，UTC',
    accepted_at DATETIME(6) NULL COMMENT 'Java落库确认时间，UTC'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交由Java提交的不可变算法提案与接收凭证';

CREATE TABLE IF NOT EXISTS godp_manual_compute (
  request_id VARCHAR(64) NOT NULL COMMENT 'Java业务任务幂等编号',
  input_hash CHAR(64) NOT NULL COMMENT '冻结输入的摘要',
  input_json LONGTEXT NOT NULL COMMENT 'Java提交的账号及选题输入快照',
  status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '计算状态pending running succeeded failed',
  result_json LONGTEXT NULL COMMENT '计算建议结果，不是正式策划记录',
  error_message VARCHAR(500) NOT NULL DEFAULT '' COMMENT '计算失败原因',
  execution_token VARCHAR(32) NULL COMMENT '执行租约令牌',
  lease_until DATETIME(6) NULL COMMENT '执行租约到期时间UTC',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '计算受理时间UTC',
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '计算更新时间UTC',
  PRIMARY KEY (request_id), KEY idx_manual_compute_pending (status, lease_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='普通人工策划计算任务，Python独占维护';
