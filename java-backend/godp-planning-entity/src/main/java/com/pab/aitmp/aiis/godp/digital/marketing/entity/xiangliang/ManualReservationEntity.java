package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang;

import com.baomidou.mybatisplus.annotation.*;

/** godp_manual_reservation，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_manual_reservation")
public class ManualReservationEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 投放日期 */
  @TableField("publish_date")
  public String publishDate;
  /** 账号唯一编号 */
  @TableField("account_id")
  public String accountId;
  /** 占用该账号日期的任务编号 */
  @TableField("task_id")
  public Long taskId;
}
