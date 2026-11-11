-- 行内模型协议适配：仅补配置，不创建新表，不切换环境，不覆盖现有地址/密钥。
-- 由 DBA/授权发布人员执行，应用启动不自动执行。
INSERT INTO godp_system_config
  (config_key,config_group,config_name,config_value,value_type,is_secret,create_by,update_by,created_by,updated_by)
VALUES
  ('MODEL_PROTOCOL','models','文本模型协议：chat_completions或doubao_native','chat_completions','string',0,'native-model-migration','native-model-migration','native-model-migration','native-model-migration'),
  ('EMBEDDING_BASE_URL','models','行内原生文本协议使用的独立向量服务前缀；待行内确认','','string',0,'native-model-migration','native-model-migration','native-model-migration','native-model-migration')
ON DUPLICATE KEY UPDATE config_key=VALUES(config_key);

-- 回退仅将本轮切换的协议、地址等恢复为发布前配置快照；不删除配置表或历史结果。
-- 本脚本只补缺省值，因此重复执行不会覆盖现场维护的配置。
