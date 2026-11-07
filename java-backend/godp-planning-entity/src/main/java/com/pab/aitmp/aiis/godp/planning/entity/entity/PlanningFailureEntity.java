package com.pab.aitmp.aiis.godp.planning.entity.entity;

import com.baomidou.mybatisplus.annotation.*;

/** godp_planning_failure，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_planning_failure")
public class PlanningFailureEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 产生失败的策划批次编号 */
  @TableField("batch_id")
  public Long batchId;
  /** 失败账号编号或批次级异常占位键 */
  @TableField("account_key")
  public String accountKey;
  /** 账号UM号昵称失败原因等展示信息 */
  @TableField("payload")
  public String payload;
}
