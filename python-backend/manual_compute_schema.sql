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
