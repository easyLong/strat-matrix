-- 旧同步副本与跨系统投递表清理：仅限本项目 strat_matrix 数据库。
-- 请用具有 DROP 权限的账号执行。执行前已备份至：
-- run/backups/retired-tables-20261030-final/restore.sql
-- 本脚本不删除策划结果、配置、标签、画像、向量、使用事实或人工任务。
USE `strat_matrix`;

DROP TABLE IF EXISTS
    `godp_account`,
    `godp_topic`,
    `godp_account_source`,
    `godp_topic_source`,
    `godp_marketing_topic_source`,
    `godp_hotspot_topic_source`,
    `godp_source_sync_run`,
    `godp_marketing_sync_run`,
    `godp_hotspot_sync_run`,
    `godp_content_history`,
    `godp_integration_outbox`,
    `godp_content_receipt`,
    `godp_publication_receipt`,
    `godp_content_production_task`;
