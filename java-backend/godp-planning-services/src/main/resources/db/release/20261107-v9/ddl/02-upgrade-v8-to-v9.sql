-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。
-- 仅适用于已完成V8且尚无V9字段的库；新库不要执行。
-- DBA发布：适用于已完成V8的业务库；应用无须DDL权限。
-- 停止业务调度后检查两列尚不存在，再执行一次；新库使用完整建表DDL。
ALTER TABLE godp_planning_batch
  ADD COLUMN write_state VARCHAR(16) NOT NULL DEFAULT 'ready'
    COMMENT '结果发布状态：staging分批写入不可见、ready完整发布',
  ADD COLUMN write_cursor INT NOT NULL DEFAULT 0
    COMMENT '自动结果已提交的明细游标，分批恢复使用';
-- 随后发布planning-query-views.sql，再部署新应用。历史批次默认ready，不改业务数据。

-- Business-owned JSON snapshots projected for SQL filtering, aggregation and pagination.
CREATE OR REPLACE VIEW godp_planning_item_read AS
SELECT i.id,i.batch_id,i.slot_id,i.account_id,i.publish_date,i.publish_week,i.payload,i.content_status,i.version,
 b.created_at AS sort_millis,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(b.payload,'$.runtime_active')),'null'),'true') AS runtime_active,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.plan_type')),'null'),'manual') AS plan_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.cycle_start')),'null'),i.publish_date) AS cycle_start,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.cycle_end')),'null'),i.publish_date) AS cycle_end,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.topic_id')),'null'),'') AS topic_id,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.topic_type')),'null'),'') AS topic_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.content_type')),'null'),'') AS content_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.slot_type')),'null'),'') AS slot_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.content_role')),'null'),'') AS content_role,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_name')),'null'),'') AS account_name,
 COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.um_no')),'null'),''),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.source_payload.um_no')),'null'),'') AS owner_um,
 COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.organization')),'null'),''),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.source_payload.organization')),'null'),'') AS organization,
 COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.platform')),'null'),''),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.source_payload.platform')),'null'),'') AS platform,
 COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.account_type')),'null'),''),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.source_payload.account_type')),'null'),'') AS account_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.lifecycle_stage')),'null'),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.lifecycle_stage')),'null'),'') AS lifecycle_stage,
 CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.followers')),'null'),NULLIF(JSON_UNQUOTE(JSON_EXTRACT(i.payload,'$.account_snapshot.followers_count')),'null'),'0') AS SIGNED) AS followers
FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id
WHERE i.del_flag='N' AND b.del_flag='N' AND b.write_state='ready';

CREATE OR REPLACE VIEW godp_planning_batch_read AS
SELECT id,payload,created_at,week_start,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.plan_type')),'null'),'manual') AS plan_type,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.cycle_start')),'null'),'') AS cycle_start,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.cycle_end')),'null'),'') AS cycle_end,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.batch_code')),'null'),'') AS batch_code,
 COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.task_name')),'null'),'') AS task_name,
 CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.account_count')),'null'),'0') AS SIGNED) AS account_count,
 CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.completed_count')),'null'),'0') AS SIGNED) AS completed_count,
 CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.failed_count')),'null'),'0') AS SIGNED) AS failed_count,
 CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.topic_count')),'null'),'0') AS SIGNED) AS topic_count
FROM godp_planning_batch WHERE del_flag='N' AND write_state='ready';

CREATE OR REPLACE VIEW godp_planning_task_read AS
SELECT CONCAT('manual:',t.id) AS row_key,t.id,'manual' AS kind,t.payload,t.created_at,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(t.payload,'$.task_name')),'') AS task_name,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(b.payload,'$.batch_code')),'') AS batch_code,
 JSON_UNQUOTE(JSON_EXTRACT(t.payload,'$.publish_date')) AS publish_date,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(t.payload,'$.created_by')),'') AS created_by,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(b.payload,'$.content_status')),'待生产') AS content_status
FROM godp_manual_task t LEFT JOIN godp_planning_batch b ON b.id=t.id AND b.del_flag='N' AND b.write_state='ready'
WHERE t.del_flag='N'
UNION ALL
SELECT CONCAT('marketing:',id),id,'marketing',topic_snapshot_json,created_at,task_name,task_code,NULL,created_by,status
FROM godp_manual_marketing_task WHERE del_flag='N'
UNION ALL
SELECT archive_key,source_id,'archive',payload,created_at,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.task_name')),''),
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.batch_code')),''),
 NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.publish_date')),'null'),
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.created_by')),''),
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.content_status')),'待生产')
FROM godp_planning_task_archive WHERE del_flag='N';
