CREATE TABLE IF NOT EXISTS godp_matching_ai_cache (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    cache_key CHAR(64) NOT NULL COMMENT '模型结果缓存唯一指纹，包含输入、词表、映射、提示词和模型版本',
    task_kind VARCHAR(32) NOT NULL COMMENT '结果种类：账号映射、选题主关联标签、需求向量或配对精判',
    model_name VARCHAR(100) NOT NULL COMMENT '生成该结果的文本或向量模型名称',
    prompt_version VARCHAR(64) NOT NULL COMMENT '提示词及模型结果校验契约版本',
    taxonomy_version INT NOT NULL COMMENT '绑定的标签词表版本',
    mapping_version INT NOT NULL COMMENT '绑定的账号映射版本',
    result_json LONGTEXT NOT NULL COMMENT '校验通过的模型结果，不保存密钥，失败结果不缓存',
    result_hash CHAR(64) NOT NULL COMMENT '模型结果完整性校验指纹',
    create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '缓存首次创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT 'matching-quality-worker' COMMENT '缓存创建进程',
    KEY idx_matching_ai_cache_kind (task_kind, model_name),
    UNIQUE KEY uk_audit_legacy_godp_matching_ai_cache (cache_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策划匹配模型结果不可变缓存';

CREATE TABLE IF NOT EXISTS godp_matching_quality_run (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除',
    created_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人',
    updated_by VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人',
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    task_id BIGINT NOT NULL COMMENT '关联现有匹配任务ID，不另建任务队列',
    lease_id CHAR(32) NOT NULL COMMENT '本次写入对应的现有匹配任务租约',
    status VARCHAR(16) NOT NULL COMMENT '质量准备状态：processing处理中、waiting分批等待、ready已就绪、failed失败',
    phase VARCHAR(32) NOT NULL COMMENT '当前阶段：选题标签、账号映射、五路召回、模型精判或分配',
    report_json LONGTEXT NOT NULL COMMENT '分批进度、主关联标签、映射证据、召回及逐对精判结果',
    report_hash CHAR(64) NOT NULL COMMENT '过程报告完整性校验指纹',
    create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '过程记录首次创建时间',
    update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '过程记录最后更新时间',
    update_by VARCHAR(50) NOT NULL DEFAULT 'matching-quality-worker' COMMENT '过程记录更新进程',
    UNIQUE KEY uk_audit_legacy_godp_matching_quality_run (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='匹配任务V19适配质量执行进度与审计';
