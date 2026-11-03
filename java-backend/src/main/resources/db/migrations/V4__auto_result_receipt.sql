-- 仅在已存在 godp_auto_planning_task 的业务库执行一次；新库使用完整建表脚本。
ALTER TABLE godp_auto_planning_task
 ADD COLUMN business_batch_id BIGINT NULL COMMENT 'Java业务库已提交的正式批次编号',
 ADD COLUMN proposal_hash CHAR(64) NULL COMMENT '已提交算法提案的SHA256指纹，用于重复确认',
 ADD COLUMN confirmation_attempts INT NOT NULL DEFAULT 0 COMMENT '落库后的Python确认请求尝试次数',
 MODIFY COLUMN status VARCHAR(24) NOT NULL COMMENT '任务状态，待发起、计算中、待确认、已完成、策划失败或旧结果已存在';
