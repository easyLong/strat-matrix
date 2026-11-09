package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang;

import com.baomidou.mybatisplus.annotation.*;

/** godp_manual_task，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_manual_task")
public class ManualTaskEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 预览编号，防重复提交 */
  @TableField("preview_code")
  public String previewCode;
  /** 业务及计算幂等编号 */
  @TableField("task_code")
  public String taskCode;
  /** 业务执行状态pending computing completed failed */
  @TableField("status")
  public String status;
  /** 任务显示字段及冻结输入 */
  @TableField("payload")
  public String payload;
  /** 业务失败原因 */
  @TableField("error_message")
  public String errorMessage;
  /** 创建时间毫秒戳 */
  @TableField("created_at")
  public Long createdAt;
  /** 更新时间毫秒戳 */
  @TableField("updated_at")
  public Long updatedAt;
}
