-- Existing strat_matrix_bus installations only. Run with the business database selected.
-- MySQL renames the six tables in one atomic RENAME TABLE statement.
RENAME TABLE
  godp_java_manual_preview TO godp_manual_preview,
  godp_java_manual_task TO godp_manual_task,
  godp_java_manual_reservation TO godp_manual_reservation,
  godp_java_planning_batch TO godp_planning_batch,
  godp_java_planning_item TO godp_planning_item,
  godp_java_planning_adjustment TO godp_planning_adjustment;

ALTER TABLE godp_manual_task RENAME INDEX idx_java_task_status TO idx_task_status;
ALTER TABLE godp_planning_item RENAME INDEX uq_java_batch_account TO uq_batch_account;
