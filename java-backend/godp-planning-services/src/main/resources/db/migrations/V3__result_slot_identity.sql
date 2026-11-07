-- Existing business database only. Verify the selected schema and back up before running once.
-- This keeps historical IDs and payloads while allowing multiple dates for one account in a batch.
ALTER TABLE godp_planning_item
  ADD COLUMN slot_id VARCHAR(128) NULL COMMENT '批次内槽位唯一编号，同账号可有多条策划' AFTER batch_id;

UPDATE godp_planning_item
SET slot_id=COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.slot_id')),''),CONCAT('LEGACY-',id))
WHERE slot_id IS NULL;

ALTER TABLE godp_planning_item
  MODIFY COLUMN slot_id VARCHAR(128) NOT NULL COMMENT '批次内槽位唯一编号，同账号可有多条策划',
  DROP INDEX uq_batch_account,
  ADD UNIQUE KEY uq_batch_slot(batch_id,slot_id),
  ADD KEY idx_result_account_date(account_id,publish_date),
  ADD KEY idx_result_batch_date(batch_id,publish_date);
