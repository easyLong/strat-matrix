package com.pab.aitmp.aiis.godp.planning.entity.entity;

import com.baomidou.mybatisplus.annotation.*;

/** godp_business_planning_config，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_business_planning_config")
public class BusinessPlanningConfigEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 配置键，当前固定为operations */
  @TableField("config_key")
  public String configKey;
  /** 当前业务配置版本号 */
  @TableField("version")
  public Integer version;
  /** 每周策划日，逗号分隔的星期数字1至7 */
  @TableField("planning_days")
  public String planningDays;
  /** 自动策划调度星期，1为周一 */
  @TableField("schedule_day")
  public Integer scheduleDay;
  /** 自动策划调度时间，24小时制HH:mm */
  @TableField("schedule_time")
  public String scheduleTime;
  /** 单营销账号每周营销内容上限 */
  @TableField("marketing_max")
  public Integer marketingMax;
  /** 热点选题占比，整数百分比 */
  @TableField("hotspot_ratio")
  public Integer hotspotRatio;
  /** 按普通营销热点配置的内容生产提前自然日JSON，空或缺项表示未配置，0为投放当天 */
  @TableField("content_production_lead_days_json")
  public String contentProductionLeadDaysJson;
  /** 最近修改时间 */
  @TableField("updated_at")
  public java.time.LocalDateTime updatedAt;
}
