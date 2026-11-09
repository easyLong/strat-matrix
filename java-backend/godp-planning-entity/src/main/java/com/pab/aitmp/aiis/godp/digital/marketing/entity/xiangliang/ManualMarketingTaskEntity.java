package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang;

import com.baomidou.mybatisplus.annotation.*;

/** godp_manual_marketing_task，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_manual_marketing_task")
public class ManualMarketingTaskEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 人工营销策划任务编号 */
  @TableField("task_code")
  public String taskCode;
  /** 前端提交幂等编号 */
  @TableField("request_id")
  public String requestId;
  /** 任务名称选题和生成数量的请求指纹 */
  @TableField("request_hash")
  public String requestHash;
  /** 策划任务名称 */
  @TableField("task_name")
  public String taskName;
  /** 选择的选题编号 */
  @TableField("topic_id")
  public String topicId;
  /** 要求生成的营销内容数量 */
  @TableField("allocation_count")
  public Integer allocationCount;
  /** 提交时的选题资料快照 */
  @TableField("topic_snapshot_json")
  public String topicSnapshotJson;
  /** 内容分配与生产状态 */
  @TableField("status")
  public String status;
  /** 内容系统已分配的账号数量 */
  @TableField("account_count")
  public Integer accountCount;
  /** 已完成的营销内容数量 */
  @TableField("content_completed_count")
  public Integer contentCompletedCount;
  /** 生成失败的营销内容数量 */
  @TableField("content_failed_count")
  public Integer contentFailedCount;
  /** 最近采纳的内容方状态时间毫秒戳 */
  @TableField("production_reported_at")
  public Long productionReportedAt;
  /** 过审内容完成投放日期编排后关联的正式批次 */
  @TableField("batch_id")
  public Long batchId;
  /** 已引用过审内容并确定投放日期的数量 */
  @TableField("linked_count")
  public Integer linkedCount;
  /** 创建时间毫秒戳 */
  @TableField("created_at")
  public Long createdAt;
  /** 更新时间毫秒戳 */
  @TableField("updated_at")
  public Long updatedAt;
}
