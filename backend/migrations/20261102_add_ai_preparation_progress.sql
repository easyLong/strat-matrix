CREATE TABLE IF NOT EXISTS godp_ai_preparation_progress (
  preparation_id BIGINT NOT NULL PRIMARY KEY COMMENT '准备任务主键，关联账号和候选选题范围',
  scope_json LONGTEXT NOT NULL COMMENT '任务固定输入范围及标签字典和模型版本，不含密钥',
  scope_hash CHAR(64) NOT NULL COMMENT '任务输入范围的完整性校验指纹',
  progress_json LONGTEXT NOT NULL COMMENT '分批准备阶段、分页断点、统计及等待原因',
  create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '任务准备进度创建时间',
  update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '任务准备进度最后更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策划任务输入范围与分批准备进度';
