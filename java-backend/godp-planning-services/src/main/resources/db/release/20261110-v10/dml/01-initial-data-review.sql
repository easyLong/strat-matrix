-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
-- 没有可擅自覆盖的通用初始配置；不包含测试账号、测试选题、密钥或批准策略。
-- 新库由业务负责人通过正式配置发布流程建立当前版本和历史，不能伪造已确认的两侧配置。
-- 存量库保持全部现有配置，本脚本只核查。
SELECT config_key,version FROM godp_business_planning_config;
SELECT COUNT(*) AS history_versions FROM godp_business_planning_config_version;
