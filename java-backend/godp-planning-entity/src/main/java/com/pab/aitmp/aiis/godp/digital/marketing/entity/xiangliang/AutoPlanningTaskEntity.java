package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang;

import com.baomidou.mybatisplus.annotation.*;

/** godp_auto_planning_task，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_auto_planning_task")
public class AutoPlanningTaskEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 目标策划周期开始日期，周一 */
  @TableField("cycle_start")
  public java.time.LocalDate cycleStart;
  /** 目标策划周期结束日期，周日 */
  @TableField("cycle_end")
  public java.time.LocalDate cycleEnd;
  /** 触发时采用的Java业务配置版本 */
  @TableField("business_config_version")
  public Integer businessConfigVersion;
  /** 触发时冻结的Java业务配置完整快照 */
  @TableField("business_config_json")
  public String businessConfigJson;
  /** 任务状态，待发起、计算中、待确认、已完成、策划失败或旧结果已存在 */
  @TableField("status")
  public String status;
  /** Python算法Pipeline运行编号 */
  @TableField("pipeline_id")
  public Long pipelineId;
  /** 过渡期Python旧正式批次编号 */
  @TableField("legacy_batch_id")
  public Long legacyBatchId;
  /** Java业务库已提交的正式批次编号 */
  @TableField("business_batch_id")
  public Long businessBatchId;
  /** 已提交算法提案的SHA256指纹，用于重复确认 */
  @TableField("proposal_hash")
  public String proposalHash;
  /** 落库后的Python确认请求尝试次数 */
  @TableField("confirmation_attempts")
  public Integer confirmationAttempts;
  /** 发起算法请求的尝试次数 */
  @TableField("attempts")
  public Integer attempts;
  /** 最近一次发起失败摘要 */
  @TableField("last_error")
  public String lastError;
  /** 任务创建时间毫秒戳 */
  @TableField("created_at")
  public Long createdAt;
  /** 任务更新时间毫秒戳 */
  @TableField("updated_at")
  public Long updatedAt;
}
