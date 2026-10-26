CREATE TABLE IF NOT EXISTS godp_manual_marketing_task (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '人工营销内容需求任务主键ID',
    task_code VARCHAR(64) NOT NULL COMMENT '人工营销内容任务唯一编号',
    request_id VARCHAR(64) NOT NULL COMMENT '客户端提交幂等标识，重复提交只创建一次',
    request_hash CHAR(64) NOT NULL COMMENT '任务名称账号和每账号条数的请求指纹',
    task_name VARCHAR(120) NOT NULL COMMENT '运营填写的策划任务名称',
    content_per_account INT NOT NULL COMMENT '每个认证账号要求生产的营销内容条数',
    account_count INT NOT NULL COMMENT '本次实际选择的去重认证账号数',
    account_snapshot_json LONGTEXT NOT NULL COMMENT '提交时校验后的账号信息快照JSON数组',
    status VARCHAR(24) NOT NULL DEFAULT '待处理' COMMENT '营销生产需求处理状态，默认待处理，不代表内容已生成或已过审',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    create_by VARCHAR(50) NOT NULL DEFAULT '运营人员' COMMENT '创建人',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    update_by VARCHAR(50) NOT NULL DEFAULT '运营人员' COMMENT '修改人',
    del_flag VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志',
    UNIQUE KEY uk_manual_marketing_code (task_code),
    UNIQUE KEY uk_manual_marketing_request (request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='人工营销内容生产需求，不预设投放日期或选择选题，审核排期独立处理';
