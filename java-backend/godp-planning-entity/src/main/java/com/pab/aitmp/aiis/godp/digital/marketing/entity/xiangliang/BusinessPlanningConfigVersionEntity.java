package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang;

import com.baomidou.mybatisplus.annotation.*;

/** godp_business_planning_config_version，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_business_planning_config_version")
public class BusinessPlanningConfigVersionEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 配置键，当前固定为operations */
  @TableField("config_key")
  public String configKey;
  /** 业务配置版本号 */
  @TableField("version")
  public Integer version;
  /** 该版本每周策划日 */
  @TableField("planning_days")
  public String planningDays;
  /** 该版本自动策划调度星期 */
  @TableField("schedule_day")
  public Integer scheduleDay;
  /** 该版本自动策划调度时间 */
  @TableField("schedule_time")
  public String scheduleTime;
  /** 该版本单营销账号每周营销内容上限 */
  @TableField("marketing_max")
  public Integer marketingMax;
  /** 该版本热点选题占比 */
  @TableField("hotspot_ratio")
  public Integer hotspotRatio;
  /** 该版本按选题类型配置的内容生产提前自然日JSON，空表示历史未记录 */
  @TableField("content_production_lead_days_json")
  public String contentProductionLeadDaysJson;
  /** 版本动作，保存或恢复 */
  @TableField("action")
  public String action;
  /** 恢复动作所引用的历史版本号 */
  @TableField("source_version")
  public Integer sourceVersion;
  /** 该版本创建时间 */
  @TableField("created_at")
  public java.time.LocalDateTime createdAt;
}
