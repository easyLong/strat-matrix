package com.pab.aitmp.aiis.godp.planning.entity.entity;

import com.baomidou.mybatisplus.annotation.*;

/** godp_planning_adjustment，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_planning_adjustment")
public class PlanningAdjustmentEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 策划明细编号 */
  @TableField("item_id")
  public Long itemId;
  /** 操作人、时间、调整前后选题及原因 */
  @TableField("payload")
  public String payload;
}
