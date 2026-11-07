-- 存量业务库升级：先停止Java服务并备份两张配置表，再执行一次。
-- 已存在该列时不要重复执行；新库使用business-planning-config.sql完整DDL。
ALTER TABLE godp_business_planning_config
  ADD COLUMN content_production_lead_days_json VARCHAR(255) NULL
  COMMENT '按普通营销热点配置的内容生产提前自然日JSON，空或缺项表示未配置，0为投放当天';
ALTER TABLE godp_business_planning_config_version
  ADD COLUMN content_production_lead_days_json VARCHAR(255) NULL
  COMMENT '该版本按选题类型配置的内容生产提前自然日JSON，空表示历史未记录';
