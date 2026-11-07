-- 内容流水扫描使用的业务库索引；启用扫描前由DBA核对现有索引后发布一次。
-- 未新增内容方的表，未复制基础资料。新库使用manual-business.sql完整DDL。
ALTER TABLE godp_planning_item ADD INDEX idx_result_content_flow_scan(content_status,id);
