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
