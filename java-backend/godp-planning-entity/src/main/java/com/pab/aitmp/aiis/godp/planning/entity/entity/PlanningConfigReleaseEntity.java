package com.pab.aitmp.aiis.godp.planning.entity.entity;

import com.baomidou.mybatisplus.annotation.*;

/** godp_planning_config_release，字段与现有DBA脚本逐列对应，不改变主键写入策略。 */
@TableName("godp_planning_config_release")
public class PlanningConfigReleaseEntity extends BaseAudit {
  private static final long serialVersionUID = 1L;
  /** 两库配置发布命令编号，重试不变 */
  @TableField("command_id")
  public String commandId;
  /** 页面综合配置版本 */
  @TableField("version")
  public Integer version;
  /** 待发布或已发布版本占用，拒绝后释放 */
  @TableField("active_version")
  public Integer activeVersion;
  /** 发布状态pending completed rejected */
  @TableField("status")
  public String status;
  /** 页面提交完整配置指纹 */
  @TableField("request_hash")
  public String requestHash;
  /** 页面综合配置快照，包含业务规则与算法参数 */
  @TableField("config_json")
  public String configJson;
  /** 发布前业务规则版本 */
  @TableField("business_expected_version")
  public Integer businessExpectedVersion;
  /** 发布前或确认后的算法配置版本 */
  @TableField("algorithm_version")
  public Integer algorithmVersion;
  /** 配置提交时间UTC字符串 */
  @TableField("created_at")
  public String createdAt;
  /** 保存、恢复或首次迁入 */
  @TableField("action")
  public String action;
  /** 恢复时引用的综合历史版本 */
  @TableField("source_version")
  public Integer sourceVersion;
  /** 配置发布失败摘要 */
  @TableField("last_error")
  public String lastError;
}
