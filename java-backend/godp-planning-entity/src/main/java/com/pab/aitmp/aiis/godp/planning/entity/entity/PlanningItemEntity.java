package com.pab.aitmp.aiis.godp.planning.entity.entity;

import com.baomidou.mybatisplus.annotation.*;

/** godp_planning_item，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_planning_item")
public class PlanningItemEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 所属批次 */
  @TableField("batch_id")
  public Long batchId;
  /** 批次内槽位唯一编号，同账号可有多条策划 */
  @TableField("slot_id")
  public String slotId;
  /** 所属账号 */
  @TableField("account_id")
  public String accountId;
  /** 投放日期 */
  @TableField("publish_date")
  public String publishDate;
  /** 投放日期所属自然周的周一，用于账号日历数据库分页 */
  @TableField("publish_week")
  public String publishWeek;
  /** 正式明细、账号及选题快照 */
  @TableField("payload")
  public String payload;
  /** 内容状态unassigned待定题 awaiting_market待营销引用 planned待生产 ready生产中 generated已完成 failed生产失败 */
  @TableField("content_status")
  public String contentStatus;
  /** 结果乐观锁版本 */
  @TableField("version")
  public Integer version;
}
