package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang;

import com.baomidou.mybatisplus.annotation.*;

/** godp_planning_resource_claim，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_planning_resource_claim")
public class PlanningResourceClaimEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 资源类型hotspot热点日占用或marketing营销内容引用 */
  @TableField("resource_kind")
  public String resourceKind;
  /** 热点投放日与选题ID组合或营销内容ID */
  @TableField("resource_key")
  public String resourceKey;
  /** 领取该资源的正式策划明细编号 */
  @TableField("item_id")
  public Long itemId;
  /** 资源绑定时间 */
  @TableField("created_at")
  public java.time.LocalDateTime createdAt;
}
