-- 仅补模型网关配置，不覆盖已有地址、模型名称或密钥。
INSERT INTO godp_system_config
  (config_key,config_group,config_name,config_value,value_type,is_secret,create_by,update_by)
VALUES
  ('MODEL_BASE_URL','models','文本与向量共用模型网关前缀；行外空值使用方舟，行内必须明确填写','','string',0,'model-endpoint-migration','model-endpoint-migration')
ON DUPLICATE KEY UPDATE config_key=VALUES(config_key);
